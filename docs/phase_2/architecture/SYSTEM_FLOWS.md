# System Flows — after Phase 2

All diagrams reflect implemented code. Phase 1 flows (registration, login/refresh/logout, subject authorization, error envelope, RLS binding) are documented in [`../phase_1/architecture/SYSTEM_FLOWS.md`](../../phase_1/architecture/SYSTEM_FLOWS.md) and remain accurate.

## 1. Canvas session bootstrap

```mermaid
sequenceDiagram
    actor U as User
    participant FE as CanvasEditor / canvasStore
    participant API as Canvas API
    participant DB as PostgreSQL

    U->>FE: "New sheet"
    FE->>API: POST /canvas/sessions {profile, device_id: devA}
    API->>DB: INSERT canvas_canvassession<br/>lock_holder=devA, generation=1, expires=now+90s
    API-->>FE: 201 session
    FE->>API: POST /canvas/pages {session, page_number:1, device_id, lock_generation:1}
    API->>DB: lock session row → ensure_lock → INSERT page
    API-->>FE: 201 page
    FE->>FE: set active page, start timers (25 s heartbeat, 3 s flush)
```

## 2. Stroke capture and offline-first persistence

```mermaid
sequenceDiagram
    actor U as User
    participant ED as Editor
    participant IDB as IndexedDB
    participant OB as Outbox

    U->>ED: pointerdown/move/up
    ED->>ED: draw segment live
    ED->>IDB: putStroke (immediate — §4)
    ED->>OB: queueOperation("strokes.append", {page_id, stroke})<br/>client_idempotency_key=UUID, client_sequence=outbox id
    Note over ED: network may be offline here — nothing else required
```

## 3. Outbox flush with idempotent replay protection

```mermaid
sequenceDiagram
    participant ED as Editor (flush loop)
    participant OB as flushOutbox()
    participant API as POST /canvas/pages/{id}/strokes
    participant DB as PostgreSQL

    ED->>OB: flushOutbox()
    OB->>OB: group pending ops per page → batch strokes[]
    OB->>API: {device_id, lock_generation, strokes[]}
    API->>DB: select_for_update session → ensure_lock
    alt all keys new
        API->>DB: savepoint-INSERT each stroke
        API-->>OB: 200 {created:[…], duplicate_keys:[]}
    else some keys already stored (replay)
        API-->>OB: 200 {created:[new], duplicate_keys:[replayed]}
    end
    OB->>OB: markAcknowledged(op ids)
```

## 4. Fencing: stale device loses the session (§5)

```mermaid
sequenceDiagram
    participant A as Device A (gen 1)
    participant B as Device B
    participant API as Canvas API

    A->>A: backgrounded — heartbeats stop
    B->>API: POST /canvas/sessions/{id}/takeover {device_id: devB}
    API-->>B: 200 generation=2, holder=devB
    A->>API: POST strokes {device_id: devA, lock_generation: 1}
    API->>API: ensure_lock: generation 1 ≠ 2
    API-->>A: 409 SESSION_LOCK_LOST envelope
    A->>A: banner shown; drawing disabled
    A->>API: POST takeover {device_id: devA} (user clicks Take over)
    API-->>A: 200 generation=3, holder=devA — resumes
```

Expiry path: a write (or heartbeat) after `lock_expires_at` also yields 409 SESSION_LOCK_LOST even if holder+generation still match.

## 5. Finalize (§67 transaction boundary)

```mermaid
flowchart TD
    A[POST /canvas/pages/{id}/finalize] --> B{lock valid?}
    B -- no --> C[409 SESSION_LOCK_LOST]
    B -- yes --> D{already finalized?}
    D -- yes --> E[200 already_finalized=true]
    D -- no --> F[BEGIN · mark finalized + finalized_at · COMMIT]
    F --> G[200 is_finalized=true]
    H[any later strokes POST] --> I[409 REVISION_CONFLICT]
```

Phase 3 will extend transaction F with document revision creation + OCR job enqueue (marked extension point in `CanvasSyncService.finalize_page`).

## 6. Heartbeat lifecycle

```text
session active ──▶ every 25 s: POST heartbeat {device_id, generation}
                        ├─ 200 → refresh expiry, adopt returned state
                        ├─ 409 SESSION_LOCK_LOST → lockLost banner
                        └─ transient error → retry next beat
tab closed / another device takes over ──▶ server lock expires after ≤90 s
```

## Not yet implemented flows (❌)

Unchanged from Phase 1: upload→OCR→canonical revisions, NoteSpace PDF, chunking/embedding/retrieval, enrichment, tags/questions/tests/chat/revision, reference books, job-producing endpoints. See [`../phase_1/architecture/SYSTEM_FLOWS.md`](../../phase_1/architecture/SYSTEM_FLOWS.md) §"Not yet implemented".
