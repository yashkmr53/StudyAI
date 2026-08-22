# Changelog

## [0.3.0] — 2026-08-22 — Phase 2: Canvas & Offline

| Field | Detail |
|---|---|
| Change | Implemented Phase 2 of the v4.1 order (§31 items 8–15): canvas domain models, fenced single-writer API, offline-first drawing editor, IndexedDB autosave, sync outbox with idempotent replay protection |
| Reason | Next phase of the implementation order; canvas is the primary input path for both product modules |
| Files/modules affected | `backend/apps/canvas/**` (models, services, serializers, views, urls, migrations), `backend/config/{urls.py,settings/base.py}`, `backend/tests/api/test_canvas.py`, `frontend/src/features/canvas/**`, `frontend/src/services/api/canvas.ts`, `frontend/src/services/sync/outbox.ts`, `frontend/src/db/indexeddb/db.ts`, `frontend/src/types/api.ts`, `frontend/src/routes/index.tsx`, `docs/phase_2/**` |
| Database migration | canvas 0001_initial · canvas 0002_enable_rls (policies on all three canvas tables) |
| API impact | Added `/api/v1/canvas/sessions[/{id}][/heartbeat,/takeover]`, `/api/v1/canvas/pages[/{id}][/strokes,/finalize]`; new error usages: 409 SESSION_LOCK_LOST, 409 REVISION_CONFLICT |
| Breaking changes | none |

### Backend

- `CanvasSession` (profile FK, optional subject SET_NULL, device tracking, lock_holder/lock_generation/lock_expires_at), `CanvasPage` (`unique(session, page_number)`), `CanvasStroke` (`page_id` + `sequence_order`, JSONB points, unique `client_idempotency_key`).
- `CanvasSessionService`: create-with-lock, ownership-scoped fetch (`select_for_update`), fencing check (holder + generation + unexpired ⇒ else 409 SESSION_LOCK_LOST), heartbeat lease refresh, forced takeover with generation increment.
- `CanvasSyncService`: lock-gated page creation; batched idempotent stroke append (savepoint create per stroke → duplicates reported, batch survives); finalize as one transaction (lock validation + immutable finalization, idempotent), with the marked Phase 3 extension point for document revision + OCR job.
- RLS migration: direct policy on sessions; EXISTS-chain policies on pages/strokes. Fixed table-name bug (`canvas_canvassession` etc.) before first apply.
- Settings: `CANVAS_LOCK_TTL_SECONDS = 90`.

### Frontend

- Canvas editor: pointer-event ink on HTML5 canvas, immediate IndexedDB persistence per stroke, outbox queueing with UUID idempotency keys, page tabs, add-page, finalize (read-only after), lock-lost banner with Take over.
- Outbox transport: grouped per-page flush via batched strokes POST; acks on success; SESSION_LOCK_LOST propagates to store and pauses flushing; triggers = 3 s interval + per-stroke + visibilitychange + beforeunload.
- Monotonic `client_sequence` now equals the outbox auto-increment id (replaces Date.now() scaffold).
- 25 s heartbeat loop adopting server session state.

### Verification

- Backend suite: 37 tests — green on PostgreSQL (37/37) and SQLite (35 pass, 2 RLS skips).
- Manual E2E through the Vite proxy: full lifecycle incl. replay duplicates, stale-generation 409, takeover fencing, post-finalize REVISION_CONFLICT.
- Frontend production build + vitest green.

## [0.2.0] — 2026-08-22 — Documentation restructure
See [`../phase_1/CHANGELOG.md`](../phase_1/CHANGELOG.md).

## [0.1.0] — 2026-08-21 — Phase 1: Security Foundation
See [`../phase_1/CHANGELOG.md`](../phase_1/CHANGELOG.md).
