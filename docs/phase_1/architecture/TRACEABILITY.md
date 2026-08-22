# Traceability — Architecture Requirement → Implementation → Test → Status

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile is tenant boundary; resources scope to profile_id (§3) | `apps/profiles/models.py`; FKs from owned resources | `tests/api/test_profiles_subjects.py` | ✅ |
| Client-supplied profile IDs never trusted (§3) | `shared/authorization/services.py::get_owned_profile/ensure_profile_access` | `test_cannot_create_subject_in_foreign_profile` | ✅ |
| Application authorization on every profile-scoped query (§3) | Querysets filter `profile__user=request.user` in both ViewSets | isolation tests | ✅ |
| RLS on profile-scoped tables (§3) | `apps/subjects/migrations/0002_enable_rls.py` | `pg_policies` check (manual) | ⚠️ policies exist; superuser bypasses locally |
| Transaction-local RLS context, not session (§3) | `shared/database/rls.py::set_profile_context` (`set_config(..., true)`) | `RLSContextTests`, `RLSContextLeakIntegrationTests` | ✅ |
| Celery workers set trusted RLS context (§3) | helper exists; no workers | — | ❌ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions in all API tests | ✅ |
| Rate limiting (§23) | — | — | ❌ |
| Audit logging (§23) | `apps/audit/` skeleton only | — | ❌ |

## Authentication

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Mature auth infra, no custom crypto (§23) | Django + SimpleJWT + Argon2 | auth flow suite | ✅ |
| Registration creates User+Profile atomically (§44.1) | `RegisterView.post` (`transaction.atomic`) | `test_register_creates_user_profile_and_tokens` | ✅ |
| Token/session revocation strategy (§23) | Refresh rotation + blacklist; logout blacklist | `test_logout_blacklists_refresh_token` | ✅ |
| Password reset (§23/§60) | `PasswordResetView` 202 stub | — | 🔧 no email/token flow |
| Never log passwords/tokens/content (§23/§25) | logging config; no sensitive fields logged | manual review | ✅ |

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| unique(user,name) Profile; unique(profile,name) Subject (§66) | migrations 0001 (both apps) | `ModelConstraintTests` | ✅ |
| UUID identity for domain rows | `models.py` UUIDField PKs | indirect | ✅ |
| Durable Job records w/ state machine (§19) | `apps/jobs/models.py` | `JobModelTests` | ✅ model; ⚠️ no producers/reaper |
| DB-level conditional claim prevents double-processing (§19) | `Job.claim()` conditional UPDATE | same | ✅ |
| Unique idempotency_key on Job (§20/§66) | field constraint | indirect | ✅ |
| Idempotency key formats (§20) | `shared/idempotency/keys.py` (+ frontend mirror) | `IdempotencyKeyTests` | ✅ formats only |
| Canonical Document/Page/Revision/Line models (§6) | — | — | ❌ |
| Source vs generated layer separation (§9) | — | — | ❌ |
| Historical attempts retained across revisions (§17/§27) | — | — | ❌ |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Stroke→page relationship via page_id + sequence_order (§4) | IndexedDB stroke records carry `page_id`, `sequence_order` | — | 🟡 client schema only; no backend models |
| Write strokes to IndexedDB immediately (§4) | `putStroke()` API exists | — | 🔧 nothing calls it (no canvas UI) |
| SyncOperation outbox w/ states (§4) | `src/db/indexeddb/db.ts`, `src/services/sync/outbox.ts` | — | 🔧 logic complete, transport unwired |
| Client idempotency keys (§4) | `crypto.randomUUID()` per op | — | 🔧 same |
| Debounce/periodic/unload flush (§4) | — | — | ❌ |
| Single-writer lock + fencing generation (§5) | — | — | ❌ |
| Finalize flow single transaction (§67) | — | — | ❌ |

## Ingestion / NoteSpace / AI

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Shared ingestion layer (§6) | — | — | ❌ |
| Logical OCR job per page/revision, primary+fallback (§6/§28) | key format only | — | ❌ |
| OCR review states + new-revision-on-edit (§48) | — | — | ❌ |
| NoteSpace faithful rendering, immutable PDFs (§7/§49) | — | — | ❌ |
| Page-aware chunking + local embeddings (§10) | — | — | ❌ |
| pgvector + tsvector hybrid retrieval with RRF (§14) | — | — | ❌ |
| Revision-aware invalidation of chunks/embeddings (§10/§27) | — | — | ❌ |
| Enrichment pipeline A–F, schema-validated (§11) | — | — | ❌ |
| Citation verification as evidence validation (§12) | — | — | ❌ |
| Generation method ⊥ citation provenance (§12) | — | — | ❌ |
| Prompt/model versioning records (§13) | dataclasses exist in `providers/base.py` | — | 🔧 types only |
| Reference-book pipeline, READY gating (§15) | — | — | ❌ |
| Chat scoped retrieval, never cross-profile (§16) | — | — | ❌ |
| Adaptive tests from mastery (§17/§55) | — | — | ❌ |
| MasteryScoringService deterministic (§18) | — | — | ❌ |
| Coalescing window / quota-aware LLM (§21/§74) | — | — | ❌ |
| Evaluation harness w/ human-labeled ground truth (§26) | — | — | ❌ |
| Provider fallback chains (§28) | protocol supports multiple impls | — | ❌ |

## Platform

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Provider abstraction; SDKs never in business logic (§24) | `providers/base.py` protocols; registry stubs | — | ✅ interfaces / 🔧 impls |
| Private object storage + short-lived signed URLs (§23) | `providers/storage/local.py` HMAC+expiring URLs | — | ⚠️ generation only; no serving route |
| OpenAPI authoritative contract (§30/§32) | drf-spectacular; committed spec | regeneration command | ✅ |
| Request IDs + structured logs (§25) | `shared/observability/request_id.py` | manual verification | ✅ |
| Observability metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32 #32) | — | — | ❌ |
| Simplest infrastructure for v1 (§32 #25) | no ES/cloud/queue runtime | — | ✅ |
| Versioned REST APIs under /api/v1 (§22) | `config/urls.py` | all API tests | ✅ |
| Async endpoints return 202 + job resource (§22) | password-reset returns 202 (not a job); no job-producing endpoints yet | — | ❌ n/a until Phase 3 |

## Counters

```text
Tracked requirements: 58
✅ 19   ⚠️ 3   🟡 1   🔧 5   ❌ 30
```
