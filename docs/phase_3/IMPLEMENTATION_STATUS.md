# Implementation Status — Phase 3

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~30% of full v4.1 scope (Phases 1–3 of 8 complete)
Completed:          Phase 1 security foundation; Phase 2 canvas/offline;
                    Phase 3 shared ingestion — canonical models, signed-URL
                    uploads w/ validation, logical OCR jobs (idempotent),
                    primary→fallback chain, job runtime (claim/retry/
                    dead-letter/reaper/jobs API), OCR review+edit revisions,
                    §67 canvas-finalize→ingestion transaction
Partial:            RLS enforcement (superuser dev bypass), reaper scheduling,
                    object storage serving (local variant)
Mocked/stubbed:     OCR providers (mock only — real provider undecided, §30),
                    password reset email, LLM/embedding registries
Unimplemented:      NoteSpace PDF renderer, chunking/embeddings/pgvector,
                    retrieval, enrichment, tags/mastery, questions/tests,
                    chat, revision planner, reference books, evaluation,
                    rate limiting, audit logging, metrics/health endpoints,
                    backups, CI, deployment artifacts
Major risks:        Mocked OCR means "recognized text" is synthetic;
                    RLS unenforced for dev superuser; no backups; no CI
```

## Phase 3 feature audit

### Canonical document models

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Document model | §6 | ✅ | `apps/documents/models.py` | `tests/api/test_documents.py` | profile FK + optional subject SET_NULL; source/source_type choices; reference_book_id plain UUID until Phase 5 | — |
| DocumentPage | §6 | ✅ | same | same | unique(document,page_number); image_ref; needs_review; ocr_status | current_revision_id is plain UUID (no circular FK) |
| DocumentPageRevision (immutable) | §6/§48 | ✅ | same | `test_user_edit_revision_is_immutable_new_revision` | unique(page,revision_number); content_hash sha256; JSON snapshot | Snapshots store mock-provider output |
| DocumentLine per revision | §6 | ✅ | same | line-count assertions | unique(revision,line_index); bbox + confidence | bboxes are synthetic from mock |
| RLS on all four tables | §3 | ⚠️ | migration `documents/0002_enable_rls.py` (EXISTS chains) | `pg_policies` verified manually | Same superuser caveat as prior phases | Behavioral restricted-role test pending |

### Upload & storage

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Create document → upload target | §45 | ✅ | `DocumentViewSet.create` returns doc+page+signed PUT URL | `UploadFlowTests` | Key namespaced by profile id | — |
| Signed upload/download serving | §23/§46 | 🟡 | `providers/storage/views.py` (token = authorization) | roundtrip + forged-token tests | Local FS stands in for direct-to-S3 (C-002) | S3 provider still absent |
| File validation (type + size) | §23 | ✅ | allow-list + `UPLOAD_MAX_BYTES` → clean `413` envelope | rejected-type + oversize tests | — | No image-content sniffing (magic-byte check) yet |
| Original never overwritten | §47 | ✅ | keys are UUID-based; new revisions get new objects where applicable | structural | — | Re-uploads to same page reuse key by design (same page slot) |

### Logical OCR job pipeline

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Finalize-upload: hash → revision → job → 202 | §46 | ✅ | `IngestionService.finalize_upload` + explicit endpoint + revisions POST mode-A | finalize suite | Returns 202 with revision+job payload | — |
| Logical job idempotency `ocr:{page}:{hash}:{pipeline}` | §6/§20 | ✅ | `shared/idempotency/keys.py` + `get_or_create_job` unique constraint | `test_duplicate_content_reuses_logical_job` | Duplicate content ⇒ same job returned | — |
| Primary → fallback attempt chain | §28 | ✅ mechanism | `providers/ocr/chain.py` | fallback + dead-letter tests | Attempts recorded in snapshot | — |
| Actual handwriting recognition | §30 open decision | 🔧 | `providers/ocr/mock.py` (`mock`, `mock_low_confidence`, `failing`) | n/a | Deterministic fake lines | Real provider unselected — deliberate |
| Worker flow incl. trusted RLS context | §47 | ✅ | `apps/jobs/services.py::run_claimed_job` wraps handler in `profile_scoped_transaction` | full-pipeline tests pass on PG | SQLite skips GUC binding (no-op) | — |
| Review states + threshold | §48 | ✅ | avg confidence < `OCR_REVIEW_THRESHOLD` (0.80) → `needs_review` on revision+page | low-confidence test | — | Threshold is a placeholder pending calibration (§26) |
| User edit → immutable new revision | §48 | ✅ | `IngestionService.create_user_revision` | edit-flow test | Old lines untouched (asserted) | Frontend editor UI arrives with Phase 4 |
| Downstream job enqueue after OCR | §47 | ❌ | extension point only | — | Chunking/embedding land in Phase 5 | — |

### Job state machine runtime

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Atomic claim (single winner) | §19 | ✅ | `Job.claim()` conditional UPDATE | claim test | — | — |
| Retry with exponential backoff + jitter | §19–20 | ✅ | `retry_backoff()`; `next_retry_at`; executor promotes due retries | dead-letter test asserts backoff set | — | — |
| Dead-letter after max attempts | §19 | ✅ | `JOBS_MAX_ATTEMPTS=3` | `test_all_failures_dead_letter_after_max_attempts` | — | — |
| Dispatch: broker / eager / DB-polling executor | §24 | ✅ | Celery task + eager inline (dev/test) + `manage.py process_jobs` polling worker | eager path exercised everywhere | Broker-free local operation proven | No real broker run yet (Redis not installed) |
| Reaper for stuck RUNNING | §19 | ⚠️ | `reap_stuck_jobs()` + `process_jobs --reap` + beat task defined | not covered by tests | Nothing schedules beat automatically locally | Add beat schedule / cron in deployment |
| Jobs API: GET /jobs/{id}, cancel | §60 | ✅ | `JobViewSet`, `CancelJobView` | shape/foreign/cancel tests | Cancel QUEUED→CANCELLED, RUNNING→CANCELLING cooperative | CANCELLING completion depends on handler checkpoints |

### Canvas ⇄ ingestion integration

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Finalize transaction (§67): lock + finalize + document + revision + OCR job | §67 | ✅ | `CanvasSyncService.finalize_page` extension | `tests/api/test_canvas_ingestion.py` | One DB transaction; storage write precedes commit (orphan risk documented) | — |
| Canvas page rasterization for ingestion | §6 input | 🟡 | `apps/canvas/raster.py` pure-stdlib PNG writer | valid-PNG unit test | Simplified renderer so canvas pages can enter OCR; NOT the NoteSpace PDF renderer | Low fidelity by design |
| One document per sheet, pages appended | §29 | ✅ | document reuse on subsequent page finalizes | `test_second_page_reuses_document` | CanvasSession.document FK links them | — |

## Carried over

Phase 1–2 features remain as audited in [`../phase_2/IMPLEMENTATION_STATUS.md`](../phase_2/IMPLEMENTATION_STATUS.md) (auth, profiles/subjects, error contract, request IDs, canvas API/UI, offline sync). Password reset still 🔧.

## Final implementation audit

```text
Total architecture requirements tracked: 71   (was 64 after Phase 2)
Fully implemented:            35
Partially implemented:         3
Simplified/alternative:        5
Mocked/stubbed:                3
Not implemented:              25

Tests passing:   backend 60/60 (PostgreSQL); 58 pass + 2 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   2 (PostgreSQL-only RLS tests under SQLite settings)
Coverage:        not measured
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          tokens in localStorage; password reset stub;
                          magic-byte file-content check absent
Known operational issues: no backups, no health endpoints, no CI,
                          reaper not auto-scheduled, no real broker run
Known AI-quality issues:  all OCR output is synthetic (mock provider);
                          review threshold uncalibrated
Known architectural deviations: local-FS storage instead of direct-to-S3 (C-002),
                          simplified rasterizer for canvas pages (C-005),
                          server-side SyncOperation table replaced by
                          stroke-level idempotency (B-001)
```
