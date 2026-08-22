# Offline Sync (Frontend)

Status: **scaffold implemented; no backend canvas/sync endpoints exist.** Nothing in the current UI writes strokes or flushes the outbox — the logic is ready and tested only by build/type-check, not by runtime flows.

## Local state: IndexedDB

`src/db/indexeddb/db.ts` opens DB `studyai` (version 1) via `idb`:

| Store | Key | Indexes | Record |
|---|---|---|---|
| `strokes` | `id` | `by_page → page_id` | `{id, page_id, sequence_order, points:number[], updated_at}` |
| `outbox` | auto-increment `id` | `by_status → status` | `SyncOperation` |

API: `putStroke`, `getStrokesForPage`, `enqueueOperation`, `pendingOperations`, `markAcknowledged`.

Relationship model follows spec §4: strokes reference `page_id` + `sequence_order`; **no** `stroke_ids[]` arrays anywhere.

## Outbox

```ts
interface SyncOperation {
  id?: number;
  device_id: string;          // persisted in localStorage (studyai.device_id)
  session_id: string;
  operation_type: string;
  client_sequence: number;    // ⚠️ currently Date.now() — simplified (A-019)
  payload: unknown;
  idempotency_key: string;    // crypto.randomUUID() per operation
  status: "pending" | "sending" | "acknowledged" | "failed" | "retrying";
  created_at: string;
  acknowledged_at?: string;
}
```

State machine:

```text
pending → sending → acknowledged
              └──→ failed → retrying → sending
```

Implemented functions (`src/services/sync/outbox.ts`):

- `queueOperation(sessionId, type, payload)` — appends a pending op.
- `flushOutbox(send)` — drains `pending` ops, calls the injected `send`, marks acknowledged on success; failures stay queued for a later flush.
- `newDeviceId()` — stable per-browser device identity.

### Honest gaps

- **Transport:** `send` is caller-supplied; no backend endpoint exists to receive ops.
- **Triggers:** no debounce/periodic/visibility-flush wiring yet (no canvas producing ops).
- **client_sequence:** timestamp-based; ties possible within the same millisecond. Replace with a monotonic per-device counter before Phase 2 sync goes live.
- **Conflict handling:** none client-side; server contract undefined until canvas API exists.

## Device lock & fencing (spec §5) — ❌ not implemented

The single-writer model with fencing generations is designed but has zero code:

```text
CanvasSession: lock_holder, lock_generation, lock_expires_at   ← no model exists
heartbeat every 20–30 s; expiry ≈ 90 s                          ← not built
write accepted iff request.lock_generation == current           ← not built
takeover increments generation                                  ← not built
```

Intended failure case (documented in the architecture, not yet executable):

```text
Device A holds session, generation = 8
Device B takes over            → generation = 9
Device A attempts a write      → generation mismatch
                               → 409 SESSION_LOCK_LOST envelope
```

`409 SESSION_LOCK_LOST` already exists as an error code in both backend (`shared/exceptions/handlers.py`) and frontend (`ApiError.code`) contracts, so clients can branch on it once fencing ships.

## Autosave rules (spec §4) — design commitments for Phase 2

- Strokes go to IndexedDB immediately (<50 ms target); network sync is decoupled.
- Debounced flush after stroke pauses + periodic fallback + flush on visibility/unload.
- Autosave never triggers OCR/LLM work.
