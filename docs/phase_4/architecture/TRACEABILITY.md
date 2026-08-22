# Traceability — Phase 4 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile is tenant boundary (§3) | FKs on all owned resources incl. digitized (via document) | isolation suites | ✅ |
| Client-supplied profile IDs never trusted (§3) | `shared/authorization/services.py` + ownership-scoped querysets everywhere | foreign-access tests | ✅ |
| App-layer authorization on all queries (§3) | per-ViewSet filtering incl. DigitizedDocumentViewSet, download view | secure-access tests | ✅ |
| RLS on profile-scoped tables (§3) | migrations across subjects/canvas/documents (6 tables) | pg_policies manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context (§3/§47) | `shared/database/rls.py`; executor binds trusted context | GUC/no-leak tests | ✅ |
| Celery workers use trusted context (§3) | `run_claimed_job` wraps handlers | pipeline tests on PG | ✅ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions | ✅ |
| File type/size validation (§23) | storage upload view | validation tests | ✅ |
| Rate limiting (§23) | — | — | ❌ |
| Audit logging (§23) | skeleton only | — | ❌ |

## Authentication

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Mature auth infra (§23) | SimpleJWT + Argon2 | auth suite | ✅ |
| Atomic registration (§44.1) | `RegisterView` | register tests | ✅ |
| Revocation strategy (§23) | rotation + blacklist + logout | logout test | ✅ |
| Password reset (§60) | 202 stub | — | 🔧 |
| No sensitive logging (§23/§25) | logging convention; job failures log errors only | manual review | ✅ |

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 unique constraints (profiles/subjects/canvas/documents) | migrations | constraint/duplicate tests | ✅ |
| UUID identities | UUIDField PKs everywhere | structural | ✅ |
| Durable jobs w/ atomic claim (§19) | `apps/jobs/models.py` + services | claim test | ✅ |
| Idempotency keys incl. live OCR + pdf usage (§20) | `shared/idempotency/keys.py`; `pdf:{doc}:{hash32}` in request_pdf | duplicate-request tests | ✅ |
| Canonical Document/Page/Revision/Line (§6) | `apps/documents/models.py` | ingestion suites | ✅ |
| Immutable revisions; edits append (§48) | `_create_revision_locked`, `create_user_revision` | immutability test | ✅ |
| Source vs generated separation (§9) | source layer complete; generated = PDF artifacts (+DigitizedDocument) | structural | 🟡 AI-generated layer still absent by phase order |
| Historical artifacts retained (§27) | superseded PDFs retained; revisions immutable | regen test asserts old retained | ✅ |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline (unchanged Phase 2 behavior)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Canvas models/constraints (§4) | `apps/canvas/models.py` | canvas suite | ✅ |
| Stroke→page relation (§4) | page_id + sequence_order both sides | structural | ✅ |
| IndexedDB-first autosave (§4) | editor pointer-up path | manual E2E | ✅ |
| Flush triggers (§4) | interval + per-stroke + visibility/unload | manual E2E | 🟡 no pause-debounce |
| Autosave never starts AI (§4) | only finalize does | structural | ✅ |
| Outbox + monotonic client_sequence + idempotency keys (§4) | `outbox.ts`, `db.ts` | replay tests (server side) | ✅ |
| Full outbox state machine (§4) | pending→acknowledged; failures stay pending | — | 🟡 |
| Client idempotency dedupe (§4) | unique stroke keys | replay test | ✅ |
| Fencing: lock/generation/expiry (§5) | `CanvasSessionService.ensure_lock` | fencing suite | ✅ |
| Heartbeat/takeover semantics (§5) | heartbeat action; takeover increments generation | takeover test | ✅ |
| Finalize transaction incl. ingestion (§67) | `finalize_page` extension | canvas-ingestion suite | ✅ |
| Server-side SyncOperation table (§29) | replaced by stroke-level keys (B-001) | replay test | 🟡 |

## Ingestion & NoteSpace (Phase 3–4 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Shared ingestion layer (§6) | `IngestionService` + storage views | upload/canvas suites | ✅ |
| Upload flow → signed target → direct upload (§45) | create + PUT roundtrip | upload tests | 🟡 local-FS stand-in for S3 |
| Upload processing → hash → revision → job → 202 (§46) | `finalize_upload` | finalize suite | ✅ |
| Logical OCR job, primary→fallback (§6/§28) | chain provider + get_or_create_job | fallback/dead-letter tests | ✅ mechanism |
| Real handwriting OCR provider | mock only | — | 🔧 §30 open |
| OCR review states (§48) | revision+page status fields | status assertions | ✅ |
| Low confidence → needs_review (§48) | threshold rule | low-confidence test | ✅ uncalibrated threshold |
| Original image never overwritten (§47) | immutable keys | structural | ✅ |
| Worker flow: RLS + idempotency + atomic lines (§47) | `run_ocr_job` | pipeline tests | ✅ |
| Downstream enqueue after OCR (chunking) (§47) | extension point only | — | ❌ |
| Retry-processing endpoint (§60) | ViewSet action | retry tests | ✅ |
| Jobs API get/cancel (§60) | `JobViewSet`, `CancelJobView` | jobs API tests | ✅ |
| Async endpoints return 202 + job (§22) | revisions/pdf/retry | asserted | ✅ |
| Storage serving views for signed URLs (§23/§45) | `providers/storage/views.py` | roundtrip/forged tests | ✅ local variant |
| Dispatch: broker/eager/executor (§24) | `dispatch_job` + `process_jobs` command | eager everywhere | ✅ |
| Retry/backoff/dead-letter (§19–20) | executor + backoff | dead-letter test | ✅ |
| Reaper stuck-RUNNING (§19) | `reap_stuck_jobs` + command flag + beat task | untested | ⚠️ not auto-scheduled |

## NoteSpace (Phase 4 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Layout-aware renderer preserving content verbatim (§7/§49) | `apps/documents/pdf_renderer.py` | purity test + artifact tests | ✅ |
| Headings only where explicitly represented (§49) | `is_heading` flag honored; never inferred | purity test flag assertion | ✅ |
| Page numbering + document metadata in PDF (§49) | footer `{page} of {nb}`; set_title/creator/subject | size/magic tests | ✅ |
| Faithful typesetting normalization only (§7) | styling differs solely for flagged headings | code-path review + tests | ✅ |
| Immutable content-addressed artifacts (§7/§27) | `DigitizedDocument` unique(document,hash); new revisions ⇒ new artifact | regen/version-change tests | ✅ |
| Renderer versioning recorded (§13-adjacent) | `RENDERER_VERSION` stored per artifact | version-change test | ✅ |
| POST /documents/{id}/pdf async (§60/§22) | ViewSet action; 200 existing / 202 enqueued | request-pdf tests | ✅ |
| GET /digitized-documents[?document=] · /{id} (§60) | list/retrieve ViewSet owner-scoped | api tests | ✅ |
| Secure PDF access: authz before signed URL (§23/§49) | `DigitizedDownloadView` + HMAC URL | foreign-user + roundtrip tests | ✅ |
| NoteSpace frontend module (upload→OCR→edit→PDF) (§63) | `features/notespace/NotespacePage.tsx` | manual E2E + build | ✅ |
| Canvas rasterization for OCR input (§6) | `raster.py` stdlib PNG writer | PNG unit test | 🟡 simplified, distinct from NoteSpace renderer |

## AI Classroom & platform remainder

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Page-aware chunking + embeddings (§10) | — | — | ❌ |
| pgvector + tsvector hybrid retrieval (§14) | — | — | ❌ |
| Revision-aware invalidation (§10/§27) | invalidation targets exist conceptually; no logic | — | ❌ |
| Enrichment pipeline A–F (§11) | — | — | ❌ |
| Citation verification (§12) | — | — | ❌ |
| Generation ⊥ provenance (§12) | ocr_provider + edited_by recorded per revision | structural start | 🟡 early fields |
| Prompt/model versioning (§13) | dataclasses; renderer_version live | — | 🔧 partial |
| Reference books (§15) | — | — | ❌ |
| Chat scoping (§16) | — | — | ❌ |
| Adaptive tests (§17/§55) | — | — | ❌ |
| MasteryScoringService (§18) | — | — | ❌ |
| Coalescing/quota-aware LLM (§21/§74) | — | — | ❌ |
| Evaluation harness (§26) | — | — | ❌ |
| Provider fallback chains (§28) | OCRChainProvider live | fallback test | ✅ OCR; others ❌ |
| Provider abstraction; SDKs isolated (§24) | protocols + registry | structural | ✅ interfaces / 🔧 impls |
| Private storage + short-lived signed URLs (§23) | local FS variant end-to-end incl. PDFs | roundtrip tests | 🟡 local variant |
| OpenAPI authoritative (§30/§32) | regenerated per phase | — | ✅ |
| Request IDs + structured logs (§25) | middleware + logs | manual | ✅ |
| Metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32) | — | — | ❌ |
| Simplest infra for v1 (§32 #25) | broker-free operation proven | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |

## Counters

```text
Tracked requirements: 78
✅ 42   ⚠️ 3   🟡 5   🔧 3   ❌ 25
```
