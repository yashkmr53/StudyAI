# Traceability — Phase 2 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile is tenant boundary; resources scope to profile_id (§3) | `apps/profiles/models.py`; canvas sessions FK profile; subjects FK profile | `tests/api/test_profiles_subjects.py`, `test_canvas.py` | ✅ |
| Client-supplied profile IDs never trusted (§3) | `shared/authorization/services.py` | foreign-profile tests (subjects + canvas sessions) | ✅ |
| Application authorization on every profile-scoped query (§3) | Querysets filter by requesting user in all ViewSets | isolation tests | ✅ |
| RLS on profile-scoped tables (§3) | migrations: `subjects/0002_enable_rls.py`, `canvas/0002_enable_rls.py` (pages/strokes via EXISTS chain) | `pg_policies` check (manual) | ⚠️ policies exist; superuser bypasses locally |
| Transaction-local RLS context (§3) | `shared/database/rls.py` | RLS GUC + no-leak tests | ✅ |
| Celery workers set trusted RLS context (§3) | helper exists; no workers | — | ❌ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions across suites | ✅ |
| Rate limiting (§23) | — | — | ❌ |
| Audit logging (§23) | skeleton only | — | ❌ |

## Authentication

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Mature auth infra, no custom crypto (§23) | Django + SimpleJWT + Argon2 | auth flow suite | ✅ |
| Registration creates User+Profile atomically (§44.1) | `RegisterView.post` | auth flow tests | ✅ |
| Token/session revocation strategy (§23) | Rotation + blacklist; logout blacklist | logout test | ✅ |
| Password reset (§23/§60) | 202 stub | — | 🔧 |
| Never log passwords/tokens/content (§23/§25) | logging config convention | manual review | ✅ |

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| unique(user,name) Profile; unique(profile,name) Subject (§66) | migrations 0001 both apps | constraint tests | ✅ |
| unique(session,page_number) CanvasPage (§66) | `canvas/0001_initial.py` | duplicate page test | ✅ |
| UUID identity for domain rows | UUIDField PKs everywhere | indirect | ✅ |
| Durable Job records w/ state machine (§19) | `apps/jobs/models.py` | claim test | ✅ model; no producers |
| DB-level conditional claim (§19) | `Job.claim()` | same | ✅ |
| Unique idempotency_key on Job (§20/§66) | field constraint | indirect | ✅ |
| Idempotency key formats (§20) | `shared/idempotency/keys.py` (+ frontend mirror) | key format tests | ✅ formats only |
| Canonical Document/Page/Revision/Line models (§6) | — | — | ❌ |
| Source vs generated layer separation (§9) | — | — | ❌ |
| Historical attempts retained across revisions (§17/§27) | — | — | ❌ |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline (Phase 2 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| CanvasSession/Page/Stroke models w/ constraints (§4) | `apps/canvas/models.py` | full canvas suite | ✅ |
| Stroke→page via page_id + sequence_order; no stroke_ids[] (§4) | models + IndexedDB record shape | structural | ✅ |
| Write strokes to IndexedDB immediately (§4) | `CanvasEditor.onPointerUp` → `putStroke` before network | manual E2E | ✅ |
| Debounce/periodic/unload flush (§4) | 3 s interval + per-stroke trigger + visibilitychange/beforeunload | manual E2E | 🟡 no explicit pause-debounce timer |
| Autosave never starts OCR/LLM (§4) | finalize defers downstream work entirely (B-004) | structural | ✅ |
| SyncOperation outbox fields incl. client_sequence + idempotency_key (§4) | `src/db/indexeddb/db.ts`, `src/services/sync/outbox.ts` | — | ✅ |
| Full outbox state machine pending→sending→acknowledged / failed→retrying (§4) | pending→acknowledged live; failures stay pending for retry | — | 🟡 failure statuses not persisted |
| Client idempotency keys prevent duplicate writes (§4) | stroke-level unique keys; server dedupes via savepoint create | replay test | ✅ |
| Single-writer lock + fencing generation (§5) | `CanvasSessionService.ensure_lock` on every write path | fencing tests | ✅ |
| Heartbeat every 20–30 s; expire ~90 s (§5) | client 25 s loop; server TTL 90 s (`CANVAS_LOCK_TTL_SECONDS`) | heartbeat + expiry tests | ✅ |
| Takeover increments generation; stale writer gets 409 SESSION_LOCK_LOST (§5) | `takeover()` + `ensure_lock` | takeover fence test | ✅ |
| Finalize flow single transaction (§67) | lock validation + finalization atomic; idempotent | finalize suite | ⚠️ doc revision + OCR job = Phase 3 extension in same transaction |
| Server-side SyncOperation records (§29 diagram) | replaced by stroke-level idempotency keys (decision B-001) | replay test | 🟡 alternative implementation |

## Ingestion / NoteSpace / AI

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Shared ingestion layer (§6) | — | — | ❌ |
| Logical OCR job per page/revision, primary+fallback (§6/§28) | key format only | — | ❌ |
| OCR review states + new-revision-on-edit (§48) | — | — | ❌ |
| NoteSpace faithful rendering, immutable PDFs (§7/§49) | — | — | ❌ |
| Page-aware chunking + local embeddings (§10) | — | — | ❌ |
| pgvector + tsvector hybrid retrieval with RRF (§14) | — | — | ❌ |
| Revision-aware invalidation (§10/§27) | — | — | ❌ |
| Enrichment pipeline A–F (§11) | — | — | ❌ |
| Citation verification as evidence validation (§12) | — | — | ❌ |
| Generation method ⊥ citation provenance (§12) | — | — | ❌ |
| Prompt/model versioning records (§13) | dataclasses in `providers/base.py` | — | 🔧 types only |
| Reference-book pipeline (§15) | — | — | ❌ |
| Chat scoped retrieval (§16) | — | — | ❌ |
| Adaptive tests from mastery (§17/§55) | — | — | ❌ |
| MasteryScoringService deterministic (§18) | — | — | ❌ |
| Coalescing window / quota-aware LLM (§21/§74) | — | — | ❌ |
| Evaluation harness w/ labeled ground truth (§26) | — | — | ❌ |
| Provider fallback chains (§28) | protocol supports multiple impls | — | ❌ |

## Platform

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Provider abstraction; SDKs never in business logic (§24) | `providers/base.py`; zero SDK imports in apps | — | ✅ interfaces / 🔧 impls |
| Private object storage + short-lived signed URLs (§23) | `providers/storage/local.py` | — | ⚠️ generation only; no serving route |
| OpenAPI authoritative contract (§30/§32) | drf-spectacular → committed spec per phase | regeneration command | ✅ |
| Request IDs + structured logs (§25) | `shared/observability/request_id.py` | manual verification | ✅ |
| Observability metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32 #32) | — | — | ❌ |
| Simplest infrastructure for v1 (§32 #25) | no ES/cloud/queue runtime | — | ✅ |
| Versioned REST APIs under /api/v1 (§22) | `config/urls.py` | all API tests | ✅ |
| Async endpoints return 202 + job resource (§22) | password-reset returns 202 (not a job); no job producers yet | — | ❌ n/a until Phase 3 |

## Counters

```text
Tracked requirements: 64
✅ 28   ⚠️ 4   🟡 3   🔧 2   ❌ 27
```
