# Implementation Status — Phase 2

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~20% of full v4.1 scope (Phases 1–2 of 8 complete)
Completed:          Phase 1 security foundation + canvas domain end-to-end:
                    models, fenced API, drawing editor, IndexedDB autosave,
                    sync outbox with idempotent replay protection
Partial:            RLS enforcement (superuser dev bypass), finalize flow
                    (document revision + OCR job deferred to Phase 3),
                    object storage serving, background jobs, observability
Unimplemented:      Ingestion/OCR, NoteSpace PDF, chunking/embeddings,
                    retrieval, enrichment, tags/mastery, questions/tests,
                    chat, revision planner, reference books, evaluation,
                    deployment artifacts
Mocked/stubbed:     Password reset email, LLM/OCR/embedding registries
Major risks:        RLS unenforced for superuser dev role; no rate limiting;
                    tokens in localStorage; no backups; no CI
```

## Phase 2 feature audit

### Canvas backend

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| CanvasSession model | §4, §29 | ✅ | `apps/canvas/models.py` | `tests/api/test_canvas.py::SessionTests` | profile FK (+optional subject), device tracking | — |
| CanvasPage model | §4 | ✅ | same | `PageTests` | `unique(session, page_number)` per §66 | — |
| CanvasStroke model | §4 | ✅ | same | `StrokeFencingTests` | `page_id` + `sequence_order`; **no** stroke_ids[]; unique client key | No styling metadata (color/width) yet |
| Session create/retrieve/list API | §60 | ✅ | `apps/canvas/views.py::CanvasSessionViewSet` | `SessionTests` | Initial lock granted to creator | — |
| Page create API | §60 | ✅ | `CanvasPageViewSet.create` → `CanvasSyncService.create_page` | `PageTests` | Lock-gated; duplicate number → 422 | — |
| Batched strokes API | §60 | ✅ | `CanvasPageViewSet.strokes` → `append_strokes` | `StrokeFencingTests` | Per-stroke `client_idempotency_key`; replay ⇒ duplicates, never new rows | — |
| Heartbeat | §5 | ✅ | `CanvasSessionService.heartbeat` | `HeartbeatTakeoverTests` | Refreshes expiry; validates holder+generation | — |
| Takeover + fencing generation | §5 | ✅ | `CanvasSessionService.takeover` | `test_takeover_increments_generation_and_fences_old_device` | Generation++ ; stale writer gets 409 SESSION_LOCK_LOST | — |
| Lock expiry (~90 s) | §5 | ✅ | `CANVAS_LOCK_TTL_SECONDS=90`; expiry checked in `ensure_lock` | `test_expired_lock_rejected` | TTL configurable via settings | No server-side reaper needed (stateless check) |
| Finalize flow | §67 | ⚠️ | `CanvasSyncService.finalize_page` | `FinalizeTests` | One transaction: lock validation + finalization; idempotent; post-finalize writes → 409 REVISION_CONFLICT | Document revision creation + OCR job enqueue land in Phase 3 inside this same transaction |
| Row locking on lock-sensitive ops | §68 | ✅ | `select_for_update()` on session row in every write path | indirect (all fencing tests) | SQLite test runs ignore FOR UPDATE (documented) | True concurrent-writer race untested |
| Canvas RLS policies | §3 | ⚠️ | migration `canvas/0002_enable_rls.py` (sessions direct; pages/strokes via EXISTS chain) | `pg_policies` verified manually | Same caveat as Phase 1: dev superuser bypasses | Behavioral enforcement test as restricted role |

### Canvas frontend

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Drawing surface | §2 canvas UI | ✅ | `src/features/canvas/CanvasEditor.tsx` (pointer events, polyline ink) | build/type-check only | Fixed 900×620 logical canvas, DPR-independent mapping | No pen styles/eraser/undo |
| Immediate IndexedDB persistence | §4 | ✅ | `putStroke()` on pointer-up before any network call | manual E2E | <50 ms target met by design (local write only) | — |
| Sync outbox queueing | §4 | ✅ | `queueOperation()` per stroke w/ UUID idempotency key | manual E2E | — | — |
| Monotonic client_sequence | §4 | ✅ | outbox auto-increment id assigned as sequence (`db.ts enqueueOperation`) | — | Replaces earlier Date.now() simplification | — |
| Grouped flush transport | §4/§60 | ✅ | `flushOutbox()` groups ops per page → single batched POST | manual E2E | Acks group on success | — |
| Flush triggers | §4 | 🟡 | 3 s interval + after each stroke + visibilitychange + beforeunload | manual | Spec's "debounce after pause" intent covered by interval+per-stroke flush; no explicit debounce timer | — |
| Outbox failure states | §4 | 🟡 | failed ops remain `pending` and retry on next flush | — | pending→acknowledged implemented; explicit `failed`/`retrying` statuses not persisted | Persist failure state + backoff in hardening phase |
| Heartbeat loop | §5 | ✅ | 25 s interval while session active (`CanvasEditor` effect) | manual | Stops on lock loss | — |
| Lock-lost UX + takeover | §5 | ✅ | banner + "Take over" button → takeover → resume with new generation | manual E2E (API level) | — | — |
| Finalized-page immutability UX | §48-adjacent | ✅ | read-only cursor/status; finalize button disabled after use | manual | — | — |
| Server-side SyncOperation records | §29 diagram | 🟡 | **Alternative:** stroke-level unique `client_idempotency_key` provides replay protection without a separate server-side op table | `test_replayed_idempotency_keys_are_duplicates_not_new_rows` | Decision B-001 | Revisit if audit/replay of raw ops is ever required |

### Carried over from Phase 1 (unchanged)

Auth foundation, profiles/subjects CRUD, error contract, request-ID logging, Job model semantics, provider protocols, local storage provider, PWA shell, auth UI — all still ✅ as documented in [`../phase_1/IMPLEMENTATION_STATUS.md`](../phase_1/IMPLEMENTATION_STATUS.md). Password reset remains 🔧 stubbed.

### Still not implemented (❌)

Ingestion/upload, OCR, canonical documents/revisions, NoteSpace PDF rendering, chunking/embeddings/pgvector/tsvector, hybrid retrieval, enrichment pipeline, citation verification, tags/mastery/questions/tests/chat/revision planner, reference books, evaluation harness, rate limiting, audit logging, health endpoints, metrics/alerts, backups, CI, deployment artifacts.

## Final implementation audit

```text
Total architecture requirements tracked: 64   (was 58 after Phase 1)
Fully implemented:            28
Partially implemented:         4
Simplified/alternative:        3
Mocked/stubbed:                2
Not implemented:              27

Tests passing:   backend 37/37 (PostgreSQL); 35 pass + 2 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   2 (PostgreSQL-only RLS tests under SQLite settings)
Coverage:        not measured (no coverage tooling configured)
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          refresh token in localStorage; password reset stub
Known operational issues: no backups, no health endpoints, no CI, no deploy artifacts
Known AI-quality issues:  N/A — no AI features implemented yet
Known architectural deviations: server-side SyncOperation table replaced by
                          stroke-level idempotency keys (B-001); finalize
                          transaction awaits Phase 3 extension (B-004)
```
