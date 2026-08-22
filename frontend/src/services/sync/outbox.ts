import { enqueueOperation, markAcknowledged, pendingOperations, type SyncOperation } from "../../db/indexeddb/db";
import { ApiError } from "../../types/api";
import { canvasApi, type LockContext } from "../api/canvas";

/**
 * Offline outbox (architecture §4):
 * pending → sending → acknowledged
 *               └──→ failed → retrying → sending
 *
 * Client idempotency keys prevent duplicate writes server-side.
 * client_sequence is the outbox auto-increment id: monotonic per device.
 */

export function newDeviceId(): string {
  const existing = localStorage.getItem("studyai.device_id");
  if (existing) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem("studyai.device_id", id);
  return id;
}

export async function queueOperation(
  sessionId: string,
  operationType: string,
  payload: unknown,
): Promise<SyncOperation> {
  const op: Omit<SyncOperation, "id"> = {
    device_id: newDeviceId(),
    session_id: sessionId,
    operation_type: operationType,
    client_sequence: 0, // replaced by the monotonic outbox id below
    payload,
    idempotency_key: crypto.randomUUID(),
    status: "pending",
    created_at: new Date().toISOString(),
  };
  const id = await enqueueOperation(op);
  return { ...op, id, client_sequence: id } as SyncOperation;
}

/* ---- transport wiring ---- */

type LockContextProvider = () => LockContext | null;
let lockContextProvider: LockContextProvider | null = null;
let onLockLostCallback: (() => void) | null = null;

/** The canvas store registers its current fencing state before flushing. */
export function registerSyncContext(provider: LockContextProvider | null, onLockLost?: () => void): void {
  lockContextProvider = provider;
  if (onLockLost) onLockLostCallback = onLockLost;
}

interface StrokeOpPayload {
  page_id: string;
  stroke: {
    id?: string;
    sequence_order: number;
    points: number[];
    client_idempotency_key: string;
  };
}

type StrokeGroup = { sessionId: string; pageId: string; opIds: number[]; strokes: StrokeOpPayload["stroke"][] };

/**
 * Flush all pending operations. Stroke ops are grouped per page into a
 * single batched POST (§60 strokes endpoint). On SESSION_LOCK_LOST the
 * remaining ops stay pending and the caller is notified via the
 * registered callback.
 */
export async function flushOutbox(): Promise<{ acked: number; lockLost: boolean }> {
  const ops = await pendingOperations();
  const groups = new Map<string, StrokeGroup>();

  for (const op of ops) {
    if (!op.id || op.operation_type !== "strokes.append") continue;
    const payload = op.payload as StrokeOpPayload;
    if (!payload?.page_id || !payload.stroke) continue;
    const key = `${op.session_id}:${payload.page_id}`;
    let group = groups.get(key);
    if (!group) {
      group = { sessionId: op.session_id, pageId: payload.page_id, opIds: [], strokes: [] };
      groups.set(key, group);
    }
    group.opIds.push(op.id);
    group.strokes.push(payload.stroke);
  }

  let acked = 0;
  for (const group of groups.values()) {
    const ctx = lockContextProvider?.();
    if (!ctx) break; // no active session/lock — retry later
    try {
      await canvasApi.pushStrokes(group.pageId, ctx, group.strokes);
    } catch (err) {
      if (err instanceof ApiError && err.code === "SESSION_LOCK_LOST") {
        onLockLostCallback?.();
        return { acked, lockLost: true };
      }
      continue; // transient failure — leave ops pending for next flush
    }
    for (const opId of group.opIds) {
      await markAcknowledged(opId);
      acked += 1;
    }
  }
  return { acked, lockLost: false };
}
