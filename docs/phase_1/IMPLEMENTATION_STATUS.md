# Implementation Status

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~10% of full v4.1 scope (Phase 1 of 8 complete)
Completed:          Auth foundation, profile/subject domain, error contract,
                    RLS policies + context helpers, Job model semantics,
                    provider interfaces, frontend auth + PWA shell,
                    IndexedDB/outbox scaffold
Partial:            RLS enforcement, background jobs, object storage,
                    offline sync, observability
Unimplemented:      Canvas, ingestion/OCR, NoteSpace PDF, chunking/embeddings,
                    retrieval, enrichment, tags/mastery, questions/tests,
                    chat, revision planner, reference books, evaluation
Mocked/stubbed:     Password reset email, LLM/OCR/embedding registries,
                    outbox transport
Major risks:        RLS unenforced for superuser dev role; no rate limiting;
                    tokens in localStorage; no backups; single-machine dev DB
```

## Module-by-module audit

### Authentication & accounts

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| User registration | §44.1, §60 | ✅ | `apps/accounts/views.py::RegisterView` | `tests/api/test_auth_flow.py` | User + default Profile in one transaction; returns token pair | — |
| Login | §60 | ✅ | `LoginView` (SimpleJWT `TokenObtainPairView`) | same | Returns `{access, refresh}` | No profile metadata in response (client fetches separately) |
| Token refresh w/ rotation+blacklist | §23 | ✅ | `TokenRefreshView`, `SIMPLE_JWT` in `config/settings/base.py` | `test_logout_blacklists_refresh_token` | 30 min access / 14 d refresh | — |
| Logout / revocation | §23 | ✅ | `LogoutView` blacklists refresh | same | Access token lives ≤30 min after | — |
| Password reset | §60 | 🔧 | `PasswordResetView` returns 202 always | none | Enumeration-safe stub | No email dispatch, no reset-token flow |
| Password hashing | §23 | ✅ | Argon2 (`PASSWORD_HASHERS` in base.py) | indirect via register tests | PBKDF2 fallback verifiers | — |

### Profiles & subjects (Phase 1 domain)

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Profile CRUD | §60 | ✅ | `apps/profiles/views.py::ProfileViewSet` | `tests/api/test_profiles_subjects.py` | Queryset filtered by requesting user | DELETE exists though spec lists it; harmless superset |
| Subject CRUD | §60 | ✅ | `apps/subjects/views.py::SubjectViewSet` | same | Ownership check on create via `ProfileAuthorizationService` | DELETE intentionally disabled |
| Unique constraints | §66 | ✅ | migrations `profiles/0001`, `subjects/0001` | `ModelConstraintTests` | DB-level, not just serializer | — |

### Authorization & isolation

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| App-layer authorization | §3 | ✅ | `shared/authorization/services.py`; per-view querysets | API isolation tests | Client-supplied profile IDs never trusted | Object-level checks for future resources reuse this service |
| RLS policies | §3 | ⚠️ | `apps/subjects/migrations/0002_enable_rls.py` on `profiles_profile`, `subjects_subject` | `pg_policies` verified manually; GUC tests | Policies exist and are correct | Dev role is superuser ⇒ PostgreSQL bypasses RLS locally; enforcement as non-superuser untested |
| Transaction-local context | §3 | ✅ | `shared/database/rls.py` (`set_config(..., true)` inside `atomic()`) | `RLSContextTests`, `RLSContextLeakIntegrationTests` | Verified no leak after commit | Celery-side usage pending workers |
| Error contract | §61 | ✅ | `shared/exceptions/handlers.py` | envelope assertions across API tests | DRF validation remapped to 422 | drf-spectacular warnings on 3 plain APIViews (schema only) |

### Background jobs

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Durable Job model | §19 | ✅ (model) | `apps/jobs/models.py` | `JobModelTests` | Full state machine fields | No rows are ever created yet — no producers |
| Atomic claim | §19 | ✅ | `Job.claim()` conditional UPDATE | same | Single-winner proven | — |
| Retry/backoff/dead-letter/reaper | §19–20 | ❌ | — | — | Helpers exist (`mark_retryable`, `dead_letter`) | No beat schedule, no reaper task |
| Celery wiring | §2 | 🔧 | `config/celery.py`; broker URL configured | — | Eager mode in tests | Redis not installed; zero tasks defined |
| Idempotency keys | §20 | ✅ (helpers) | `shared/idempotency/keys.py` | `IdempotencyKeyTests` | Formats match spec exactly | Not yet used by any job |

### Providers & storage

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Provider protocols | §24, §64 | ✅ (interfaces) | `providers/base.py` | — | OCR/LLM/Embedding/ObjectStorage protocols | Business logic doesn't call them yet |
| Provider registry | §24 | 🔧 | `providers/registry.py` raises `NotImplementedError` | — | Explicit stubs | Real providers arrive Phases 3/5/6 |
| Local object storage | §23 | ⚠️ | `providers/storage/local.py` (HMAC-signed expiring URLs) | — | Signed URL generation works | **No serving views routed**; unused by any flow; path-traversal guard present |

### Ingestion / OCR / NoteSpace / AI Classroom

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Document/Page/Revision/Line models | §6 | ❌ | — | — | — | Phase 3 |
| Upload flow + direct-to-storage | §45 | ❌ | — | — | — | Phase 3 |
| Logical OCR job, primary/fallback | §6, §47 | ❌ | — | — | Key format only (`shared/idempotency/keys.py`) | Phase 3 |
| NoteSpace renderer/PDF | §7, §49 | ❌ | — | — | — | Phase 4 |
| Chunking/embeddings/pgvector/tsvector | §10, §14 | ❌ | — | — | pgvector extension not installed | Phase 5 |
| Hybrid retrieval + RRF | §14 | ❌ | — | — | — | Phase 5 |
| Enrichment pipeline A–F | §11 | ❌ | — | — | — | Phase 6 |
| Citation verification | §12 | ❌ | — | — | — | Phase 6 |
| Tags/mastery/questions/tests/chat/revision | §16–18 | ❌ | app skeletons only | — | Empty apps registered in `INSTALLED_APPS` | Phase 7 |
| Reference books | §15 | ❌ | — | — | — | Phase 5 |

### Frontend

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| PWA scaffold | §63 | ✅ | `vite.config.ts` (vite-plugin-pwa), manifest, SW | build passes | Precache + auto-update | No offline page UX |
| Auth UI + session | §44.1 | ✅ | `src/features/auth/*`, zustand store | manual E2E | Tokens persisted in localStorage | XSS-sensitive storage choice |
| API client | §61 | ✅ | `src/services/api/client.ts` | smoke test only | Auto refresh-retry once on 401; typed `ApiError` | No request retry/backoff for 5xx |
| Route guard/layout | §63 | ✅ | `src/routes/index.tsx`, `src/components/Layout.tsx` | — | — | — |
| IndexedDB stores | §4 | 🟡 | `src/db/indexeddb/db.ts` | — | strokes + outbox stores with indexes | Schema only; nothing writes strokes yet (no canvas) |
| Sync outbox | §4 | 🔧 | `src/services/sync/outbox.ts` | — | queue/flush logic complete | `send` transport not wired (no backend endpoints); `client_sequence` uses `Date.now()` (simplified vs monotonic counter) |
| Canvas drawing surface | §4 | ❌ | — | — | Placeholder route only | Phase 2 |
| Module pages | §1 | 🔧 | `Placeholder.tsx` routes | — | Explicit placeholders | Phases 4–7 |

### Operations

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Request IDs + structured logs | §25 | ✅ | `shared/observability/request_id.py`, LOGGING in base.py | manual | ID in header, logs, error envelope | — |
| Metrics/health endpoints/alerts | §25 | ❌ | — | — | — | Phase 8 |
| OpenAPI contract | §32 #24/#30 | ✅ | drf-spectacular → `docs/phase_1/openapi.yaml` | generation in CI-less workflow | Regenerate: `manage.py spectacular` | 3 schema warnings (plain APIViews) |
| Rate limiting | §23 | ❌ | — | — | 429 code reserved | Pre-production requirement |
| Audit logging | §23 | ❌ | `audit` app skeleton | — | — | Phase 8 |
| Backups/DR | §70 | ❌ | — | — | — | Phase 8 exit criterion |
| Deployment artifacts | §24 | ❌ | prod settings exist only | — | — | No Dockerfile/compose/CI |

## Final implementation audit

Counts derived row-by-row from [architecture/TRACEABILITY.md](architecture/TRACEABILITY.md).

```text
Total architecture requirements tracked: 58
Fully implemented:            19
Partially implemented:         3
Simplified/alternative:        1
Mocked/stubbed:                5
Not implemented:              30

Tests passing:   backend 17/17 (PostgreSQL); 15 pass + 2 skip (SQLite)
                 frontend 1/1 (vitest)
Tests failing:   0
Tests skipped:   2 (PostgreSQL-only RLS tests under SQLite settings)
Coverage:        not measured (no coverage tooling configured)
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          refresh token in localStorage; password reset is a stub
Known operational issues: no backups, no health endpoints, no CI, no deploy artifacts
Known AI-quality issues:  N/A — no AI features implemented yet
Known architectural deviations: see ASSUMPTIONS_AND_DECISIONS.md (all minor,
                          none contradict v4.1 invariants)
```
