# Offline Sync — as actually built (Phase 2)

Status: **implemented end-to-end** for stroke capture and sync. The editor, IndexedDB persistence, outbox transport, and fenced backend all exist and were exercised manually through the running stack.

## Local state: IndexedDB (`studyai` v1)

| Store | Key | Indexes | Record |
|---|---|---|---|
| `strokes` | `id` | `by_page → page_id` | `{id, page_id, sequence_order, points:number[], updated_at}` |
| `outbox` | auto `id` | `by_status → status` | `SyncOperation` |

## SyncOperation

```ts
{
  id: number;                 // outbox auto-increment
  device_id: string;          // persisted per browser
  session_id: string;
  operation_type: "strokes.append";
  client_sequence: number;    // = outbox id → monotonic per device (B-011)
  payload: { page_id, stroke };
  idempotency_key: string;    // UUID per operation
  status: "pending" | "sending" | "acknowledged" | "failed" | "retrying";
  created_at: string;
  acknowledged_at?: string;
}
```

State machine as implemented:

```text
pending → acknowledged            (batch acked after server 200)
   └── failures remain pending     → retried on next flush
```

🟡 The spec's explicit `failed`/`retrying` persisted states are not yet written; failure handling is implicit (stay-pending + retry). Dead-lettering does not exist — a permanently failing op would retry forever until the page/session is removed.

## Capture path (§4)

```text
pointerup
  → putStroke to IndexedDB           (immediate; network-independent)
  → queueOperation to outbox         (UUID idempotency key)
  → trigger flushOutbox()
```

Autosave never starts OCR/LLM work — only the explicit Finalize action talks to finalize, which itself defers downstream work to Phase 3.

## Flush transport

`flushOutbox()` (`src/services/sync/outbox.ts`):

1. Reads all `pending` ops.
2. Groups `strokes.append` ops by `session_id + page_id`.
3. For each group: asks the registered lock-context provider for `{device_id, lock_generation}`; skips if absent.
4. Sends one batched `POST /canvas/pages/{id}/strokes`.
5. On success: marks every op in the group acknowledged.
6. On `409 SESSION_LOCK_LOST`: invokes the registered callback (store sets `lockLost`) and stops flushing — ops stay pending.
7. Other errors: group stays pending; next flush retries.

Triggers: 3 s interval, after each finished stroke, `visibilitychange`, `beforeunload`. 🟡 No explicit pause-debounce timer (the interval + per-stroke trigger cover the intent).

## Heartbeat & fencing UX (§5)

- 25 s heartbeat loop while a session is active; adopts returned session state.
- Any `SESSION_LOCK_LOST` (heartbeat, flush, or user action) → banner: *"This sheet is now controlled by another device."* with a **Take over** button.
- Take over → `POST takeover` → generation increments → editor resumes; pending outbox ops flush against the new generation.

```text
Device A gen=1 ── backgrounded
Device B takeover      → gen=2, holder=B
Device A write         → 409 SESSION_LOCK_LOST → banner
Device A "Take over"   → gen=3, holder=A → resumes
```

## Conflict handling

- Duplicate writes: impossible via unique client keys (server reports duplicates).
- Concurrent single-writer conflicts: prevented by fencing.
- Offline-created strokes: sequence_order is client-assigned per page; ordering across devices after takeover follows each device's local counters — acceptable v1 behavior, documented as such.

## Known gaps

1. Failure statuses not persisted (see above).
2. No compression/batching limits — very large flush batches are sent whole.
3. No UI indicator of pending-op count / offline state.
4. Multi-tab same-device concurrency relies on the same fencing (each tab has its own device_id? no — shared localStorage device_id; two tabs drawing simultaneously will fence each other via generation checks).
