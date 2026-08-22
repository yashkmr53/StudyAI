import { openDB, type IDBPDatabase } from "idb";

/**
 * Local-first storage (architecture §2, §4):
 * - strokes are written to IndexedDB immediately
 * - the sync outbox queues operations for the backend
 */
const DB_NAME = "studyai";
const DB_VERSION = 1;

export interface SyncOperation {
  id?: number;
  device_id: string;
  session_id: string;
  operation_type: string;
  client_sequence: number;
  payload: unknown;
  idempotency_key: string;
  status: "pending" | "sending" | "acknowledged" | "failed" | "retrying";
  created_at: string;
  acknowledged_at?: string;
}

export interface StrokeRecord {
  id: string;
  page_id: string;
  sequence_order: number;
  points: number[];
  updated_at: string;
}

let dbPromise: Promise<IDBPDatabase> | null = null;

function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains("strokes")) {
          const strokes = db.createObjectStore("strokes", { keyPath: "id" });
          strokes.createIndex("by_page", "page_id");
        }
        if (!db.objectStoreNames.contains("outbox")) {
          const outbox = db.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
          outbox.createIndex("by_status", "status");
        }
      },
    });
  }
  return dbPromise;
}

export async function putStroke(stroke: StrokeRecord): Promise<void> {
  const db = await getDb();
  await db.put("strokes", stroke);
}

export async function getStrokesForPage(pageId: string): Promise<StrokeRecord[]> {
  const db = await getDb();
  return db.getAllFromIndex("strokes", "by_page", pageId);
}

export async function enqueueOperation(op: Omit<SyncOperation, "id">): Promise<number> {
  const db = await getDb();
  const id = (await db.add("outbox", op)) as number;
  // client_sequence becomes the monotonic outbox id (per-device ordering)
  await db.put("outbox", { ...op, id, client_sequence: id });
  return id;
}

export async function pendingOperations(): Promise<SyncOperation[]> {
  const db = await getDb();
  return db.getAllFromIndex("outbox", "by_status", "pending");
}

export async function markAcknowledged(id: number): Promise<void> {
  const db = await getDb();
  await db.put("outbox", {
    ...(await db.get("outbox", id)),
    status: "acknowledged",
    acknowledged_at: new Date().toISOString(),
  });
}

export async function updateOperationStatus(id: number, status: SyncOperation["status"]): Promise<void> {
  const db = await getDb();
  const op = await db.get("outbox", id);
  if (op) {
    await db.put("outbox", { ...op, status });
  }
}

export async function getOperationsByStatus(status: SyncOperation["status"]): Promise<SyncOperation[]> {
  const db = await getDb();
  return db.getAllFromIndex("outbox", "by_status", status);
}
