# Traceability — Phase 3 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile is tenant boundary (§3) | FKs on profiles/subjects/canvas/documents | isolation suites | ✅ |
| Client-supplied profile IDs never trusted (§3) | `shared/authorization/services.py` | foreign-profile tests | ✅ |
| App-layer authorization on all queries (§3) | per-ViewSet queryset filtering incl. documents/jobs | isolation tests | ✅ |
| RLS on profile-scoped tables (§3) | migrations: subjects, canvas, documents (+EXISTS chains) | `pg_policies` manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context (§3) | `shared/database/rls.py` (PG-only no-op on SQLite) | GUC + no-leak tests | ✅ |
| Celery workers set trusted RLS context (§3/§47) | executor wraps handlers in `profile_scoped_transaction` | full-pipeline tests on PG | ✅ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | across suites | ✅ |
| File type/size validation (§23) | upload view allow-list + `UPLOAD_MAX_BYTES` → 413 envelope | rejected-type, oversize tests | ✅ |
| Rate limiting (§23) | — | — | ❌ |
| Audit logging (§23) | skeleton only | — | ❌ |

## Authentication

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Mature auth infra (§23) | SimpleJWT + Argon2 | auth suite | ✅ |
| Atomic registration (§44.1) | `RegisterView` | register tests | ✅ |
| Revocation strategy (§23) | rotation + blacklist + logout | logout test | ✅ |
| Password reset (§60) | 202 stub | — | 🔧 |
| No sensitive logging (§23/§25) | logging convention | manual review | ✅ |

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 unique constraints (profile/subject/canvas) | migrations 0001s | constraint + duplicate tests | ✅ |
| unique(document,page_number) / (page,revision_number) / (revision,line_index) (§66) | `documents/0001_initial.py` | finalize/edit suites | ✅ |
| UUID identities | UUIDField PKs everywhere | structural | ✅ |
| Durable Job records + atomic claim (§19) | `apps/jobs/models.py` | claim test | ✅ |
| Idempotency key formats (§20) | `shared/idempotency/keys.py`; OCR key used live | format tests + duplicate-finalize test | ✅ |
| Canonical Document/Page/Revision/Line models (§6) | `apps/documents/models.py` | ingestion suites | ✅ |
| Immutable revisions; edits create new revisions (§48) | `_create_revision_locked`, `create_user_revision` | edit immutability test | ✅ |
| Source vs generated layer separation (§9) | only source layer exists so far | — | 🟡 partial by phase order |
| Historical artifacts retained (§17/§27) | revisions never mutated/deleted | immutability test | ✅ for revisions; ❌ questions/mastery n/a |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| CanvasSession/Page/Stroke + constraints (§4) | `apps/canvas/models.py` | canvas suite | ✅ |
| Stroke→page via page_id + sequence_order (§4) | models + IndexedDB shape | structural | ✅ |
| Immediate IndexedDB persistence (§4) | editor pointer-up path | manual E2E | ✅ |
| Flush triggers (§4) | interval + per-stroke + visibility/unload | manual E2E | 🟡 no pause-debounce |
| Autosave never starts AI work (§4) | only finalize triggers pipeline | structural | ✅ |
| Outbox fields + monotonic client_sequence (§4) | `db.ts`, `outbox.ts` | — | ✅ |
| Full outbox state machine (§4) | pending→acknowledged; failures stay pending | — | 🟡 |
| Client idempotency prevents dupes (§4) | stroke-level keys + server dedupe | replay test | ✅ |
| Fencing: single writer, generation checks (§5) | `CanvasSessionService.ensure_lock` | fencing suite | ✅ |
| Heartbeat/expiry (§5) | 25 s client / 90 s TTL | heartbeat + expiry tests | ✅ |
| Takeover fences stale writers (§5) | takeover + ensure_lock | takeover test | ✅ |
| Finalize transaction: lock+finalize+document+revision+OCR job (§67) | `CanvasSyncService.finalize_page` extension | `test_canvas_ingestion.py` | ✅ |
| Server-side SyncOperation table (§29) | replaced by stroke idempotency (B-001) | replay test | 🟡 |

## Ingestion (Phase 3 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Shared ingestion layer: photo/canvas → canonical document (§6) | `IngestionService` + storage views | upload + canvas-ingestion suites | ✅ |
| Upload flow: create doc/page → signed target → direct upload (§45) | `DocumentViewSet.create` + storage views | upload roundtrip tests | 🟡 local-FS stand-in for S3 |
| Upload processing: validate → hash → revision → job → 202 (§46) | `finalize_upload` + explicit endpoint | finalize suite | ✅ |
| Logical OCR job per page/revision w/ primary→fallback (§6/§28) | `enqueue_ocr_job` + `OCRChainProvider` | fallback test | ✅ mechanism |
| Real handwriting OCR provider | mock only (`providers/ocr/mock.py`) | — | 🔧 §30 open decision |
| OCR review states pending/processing/completed/needs_review/failed (§48) | revision+page status fields | status assertions | ✅ |
| Low confidence → needs_review (§48) | threshold check in `run_ocr_job` | low-confidence test | ✅ threshold uncalibrated |
| Original image never overwritten (§47) | immutable object keys | structural | ✅ |
| Worker: RLS context + idempotency + atomic lines + status (§47) | `run_ocr_job` under executor scope | pipeline tests | ✅ |
| Downstream enqueue after OCR (chunking) (§47) | extension point only | — | ❌ Phase 5 |
| Retry-processing endpoint (§60) | `DocumentViewSet.retry_processing` | retry tests | ✅ |
| Jobs API GET/{id} + cancel (§60) | `JobViewSet`, `CancelJobView` | jobs API tests | ✅ |
| Async endpoints return 202 + job resource (§22) | finalize-upload/revisions/retry return 202 | asserted | ✅ |
| Storage serving views for signed URLs (§23/§45) | `providers/storage/views.py` | roundtrip/forged tests | ✅ local variant |
| Job dispatch: broker/eager/executor (§24) | `dispatch_job` + eager + `process_jobs` command | eager everywhere | ✅ |
| Retry/backoff/dead-letter (§19–20) | `retry_backoff`, promote, dead-letter | dead-letter test | ✅ |
| Reaper stuck-RUNNING requeue (§19) | `reap_stuck_jobs` + `process_jobs --reap` + beat task | untested | ⚠️ not auto-scheduled |

## NoteSpace / AI Classroom

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| NoteSpace faithful renderer + PDFs (§7/§49) | simplified rasterizer exists for ingestion input only | PNG unit test | 🟡 rasterizer ≠ NoteSpace renderer; ❌ PDF |
| Page-aware chunking + embeddings (§10) | — | — | ❌ |
| pgvector + tsvector hybrid retrieval (§14) | — | — | ❌ |
| Revision-aware invalidation (§10/§27) | — | — | ❌ |
| Enrichment pipeline A–F (§11) | — | — | ❌ |
| Citation verification (§12) | — | — | ❌ |
| Generation ⊥ provenance (§12) | generation_method field planned; ocr_provider recorded per revision | structural start | 🟡 early fields only |
| Prompt/model versioning (§13) | dataclasses in `providers/base.py`; provider recorded per revision | — | 🔧 types only |
| Reference books (§15) | — | — | ❌ |
| Chat scoping (§16) | — | — | ❌ |
| Adaptive tests (§17/§55) | — | — | ❌ |
| MasteryScoringService (§18) | — | — | ❌ |
| Coalescing/quota-aware LLM (§21/§74) | — | — | ❌ |
| Evaluation harness (§26) | — | — | ❌ |
| Provider fallback chains (§28) | `OCRChainProvider` live | fallback test | ✅ for OCR; LLM/embeddings ❌ |

## Platform

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Provider abstraction; SDKs isolated (§24) | protocols + registry; apps import interfaces only | structural | ✅ interfaces / 🔧 impls |
| Private storage + short-lived signed URLs (§23) | HMAC-signed expiring URLs; token = authorization | forged/expiry paths | 🟡 local FS variant |
| OpenAPI authoritative (§30/§32) | regenerated per phase | — | ✅ |
| Request IDs + structured logs (§25) | middleware + formatter | manual | ✅ |
| Metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32) | — | — | ❌ |
| Simplest infra for v1 (§32 #25) | broker-free local operation proven via executor | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |

## Counters

```text
Tracked requirements: 71
✅ 35   ⚠️ 3   🟡 5   🔧 3   ❌ 25
```
