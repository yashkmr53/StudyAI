# Assumptions and Decisions — Phase 2

Phase 1 decisions (A-001…A-020) remain in force: [`../phase_1/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../../phase_1/architecture/ASSUMPTIONS_AND_DECISIONS.md). This page records Phase 2 decisions (B-series).

| ID | Decision |
|---|---|
| B-001 | No server-side `SyncOperation` table; replay protection via unique per-stroke `client_idempotency_key`. |
| B-002 | Lock TTL = 90 s server-side (`CANVAS_LOCK_TTL_SECONDS`); client heartbeats every 25 s. |
| B-003 | Takeover is unconditional for the owning user (no "active lock holder consent"). |
| B-004 | Finalize transaction covers lock validation + finalization only; document revision + OCR job enqueue deferred to Phase 3 inside the same transaction. |
| B-005 | Stroke geometry stored as a flat JSON number array `[x0,y0,x1,y1,…]`; no styling metadata yet. |
| B-006 | Every lock-sensitive write locks the session row (`select_for_update`) rather than the page/stroke rows. |
| B-007 | RLS on pages/strokes uses EXISTS subquery policies chained to the session's profile. |
| B-008 | Strokes POST accepts a **batch** with mixed create/duplicate outcomes (200 + counts) instead of one-stroke-per-request. |
| B-009 | Writes to a finalized page return `409 REVISION_CONFLICT`; finalize itself is idempotent (200, `already_finalized`). |
| B-010 | Drawing implemented with raw HTML5 Canvas 2D + pointer events; no canvas library (konva/fabric). |
| B-011 | Client `client_sequence` = outbox auto-increment id (monotonic per device), replacing the Phase 1 scaffold's `Date.now()`. |
| B-012 | Outbox failure handling keeps ops `pending` and retries on the next flush; explicit failed/retrying statuses are not persisted yet. |

---

## Details

### B-001 — Idempotency without a server-side op table
- **Context:** §29 diagrams `SyncOperation` under CanvasSession; §4 requires client idempotency keys to prevent duplicate writes.
- **Decision:** the stroke row itself carries the client key (unique constraint). Replays hit the key constraint and are reported as duplicates.
- **Alternatives:** dedicated sync-op table storing every received operation.
- **Consequences:** fewer tables/joins; no server-side audit of raw operation stream. If op-level audit is ever needed, add the table then.
- **Architecture impact:** satisfies §4's duplicate-write guarantee; deviation from §29's diagram shape recorded.

### B-002 — Lock timing
- **Why:** spec fixes expiry ≈ 90 s and heartbeat 20–30 s; 25 s gives >3 missed beats before expiry.
- **Consequences:** clock skew between devices is irrelevant (server clock authoritative); a backgrounded tab that misses ~4 beats loses the lock and must take over.

### B-003 — Forced takeover
- **Context:** single-writer v1; all devices belong to the same authenticated user.
- **Alternatives:** require the old holder's release, or an expiry wait.
- **Consequences:** generation++ fences the old device immediately; matches §5's takeover semantics.

### B-004 — Finalize scope
- **Why:** document/OCR models don't exist until Phase 3; deferring keeps Phase 2 honest while preserving the §67 transaction boundary as a single extension point (`finalize_page` contains the marked location).
- **Impact:** finalize is ⚠️ partial vs §67 by design.

### B-006 — Session-row locking
- **Why:** fencing state lives on the session; locking it serializes all writes to that session's pages, guaranteeing check-then-write atomicity.
- **Consequences:** SQLite ignores FOR UPDATE in tests → true race coverage arrives with PostgreSQL CI runs; logic is row-state based and fully tested.

### B-008 — Batched strokes endpoint
- **Why:** outbox flushes group many small ops; batching cuts request count and lets replays report per-key duplicates in one round trip.
- **Semantics:** 200 always (unless lock/validation fails); body lists created ids and duplicate keys.

### B-010 — No canvas framework
- **Why:** current needs (single ink color, polyline strokes) are trivial; libraries add weight and migration risk before requirements stabilize.
- **Revisit:** if pressure sensitivity/palm rejection tooling is needed, evaluate perfect-freehand/pointerevents helpers then.
