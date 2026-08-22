# Changelog

## [0.4.0] — 2026-08-22 — Phase 3: Shared Ingestion

| Field | Detail |
|---|---|
| Change | Implemented Phase 3 of the v4.1 order (§31 items 16–24): canonical document models, signed-URL upload flow with validation, logical OCR jobs with primary→fallback chain, job runtime (dispatch/retry/dead-letter/reaper/jobs API), OCR review + user-edit revisions, §67 canvas-finalize→ingestion transaction |
| Reason | Next phase of the implementation order; ingestion is the shared boundary feeding NoteSpace and AI Classroom |
| Files/modules affected | `backend/apps/documents/**` (new app), `backend/apps/jobs/**` (services/tasks/executor/management command/migration), `backend/providers/{ocr,storage}/**`, `backend/apps/canvas/{models,services,raster,migrations}`, `backend/config/{urls.py,settings/base.py,settings/dev.py}`, `backend/tests/api/test_documents.py`, `backend/tests/api/test_canvas_ingestion.py`, `docs/phase_3/**` |
| Database migration | documents 0001_initial · documents 0002_enable_rls · canvas 0003_canvassession_document · jobs 0002_job_next_retry_at |
| API impact | Added `/documents` CRUD+actions (pages/revisions/retry-processing), `/documents/pages/{id}/finalize-upload`, `/jobs/{id}`, `/jobs/{id}/cancel`, `/storage/upload/{key}` PUT, `/storage/download/{key}` GET; 202-with-job semantics now live; new error usages: 413 payload too large |
| Breaking changes | none |

### Backend — ingestion

- Canonical models: Document (source upload/canvas/reference, schema_version), DocumentPage (unique per doc+number, image_ref, needs_review, ocr_status), immutable DocumentPageRevision (sha256 content_hash, JSON snapshot, ocr_provider), DocumentLine (unique per revision+index, bbox, confidence). RLS policies on all four tables.
- Upload flow: POST /documents → doc + page + HMAC-signed PUT target; storage serving views validate signature/expiry/action/key, content-type allow-list, size cap (clean 413).
- finalize-upload: object read → sha256 → revision(n+1) → logical OCR job `ocr:{page}:{hash}:{pipeline}` (get-or-create; duplicates reuse the job) → dispatch → **202**.
- run_ocr_job worker flow: trusted RLS context, completed short-circuit, primary→fallback chain, atomic line persistence, needs_review below threshold, snapshot with attempted providers.
- §48 edits: lines-array revisions create immutable new revisions attributed to the editor.

### Backend — jobs runtime

- get_or_create_job / dispatch_job (eager inline for dev/test; broker otherwise, failure tolerated) / atomic claim / retry backoff via next_retry_at / dead-letter at JOBS_MAX_ATTEMPTS / reap_stuck_jobs / `process_jobs [--loop --reap]` DB-polling executor.
- Jobs API: owner-scoped GET /jobs/{id}; cancel (QUEUED→CANCELLED, RUNNING→CANCELLING cooperative).

### Backend — canvas integration

- CanvasSession.document FK (SET_NULL); finalize_page now completes §67: lock check + finalization + pure-stdlib PNG rasterization (`apps/canvas/raster.py`) + storage write + Document/Page/Revision/Job creation in one transaction; one document per sheet, pages appended; idempotent re-finalize.

### Settings

OCR_PIPELINE_VERSION=mock-v1 · OCR_PROVIDER_CHAIN=[mock,mock] · OCR_REVIEW_THRESHOLD=0.80 · UPLOAD_MAX_BYTES=10MB (+ DATA_UPLOAD_MAX_MEMORY_SIZE headroom) · UPLOAD_ALLOWED_CONTENT_TYPES · JOBS_MAX_ATTEMPTS=3 · retry base/cap · JOBS_TIMEOUT_SECONDS=600 · dev: CELERY_TASK_ALWAYS_EAGER=True.

### Verification

Backend suite: 60 tests — green on PostgreSQL (60/60) and SQLite (58 pass + 2 RLS skips). Manual E2E through the Vite proxy: photo upload → signed PUT → finalize → completed OCR; canvas strokes → finalize → document/revision/job chain. Frontend build + vitest green.

## [0.3.0] — Phase 2 · [0.2.0] — Docs restructure · [0.1.0] — Phase 1
See [`../phase_2/CHANGELOG.md`](../phase_2/CHANGELOG.md) and [`../phase_1/CHANGELOG.md`](../phase_1/CHANGELOG.md).
