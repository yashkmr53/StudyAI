# Testing — after Phase 3

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=2): 60 found — 58 passed, 2 skipped

# Backend — integration profile (real PostgreSQL)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests
# → OK: 60 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    60 total  (+23 new in Phase 3)
  Passing:        60 (PostgreSQL)
  Failing:        0
  Skipped:        2 under SQLite only (PostgreSQL-only RLS tests)
Frontend tests:   1 passing; production build green
Coverage:         not measured
```

## Phase 3 test inventory

### `tests/api/test_documents.py` (20 tests)

| Suite | Proves |
|---|---|
| `UploadFlowTests` (7) | upload target shape; foreign-profile 403; PUT→signed-URL→download roundtrip byte-equality; disallowed content-type 422; oversize 413 envelope; forged token 403 |
| `FinalizeAndOcrTests` (7) | finalize → revision 1 + job succeeded + 3 lines + page completed; duplicate content ⇒ same logical job id (§20); low-confidence chain ⇒ needs_review on page+revision; failing primary ⇒ fallback used with attempted-providers recorded; all-fail ⇒ retryable with backoff then dead-letter at max attempts; user edit ⇒ new immutable revision, old lines untouched; cross-user 404 |
| `RetryProcessingTests` (2) | failed job reset → re-run to success; succeeded job retry → 422 |
| `JobsApiTests` (4) | job payload shape; foreign job 404; terminal cancel 422; queued cancel → cancelled |

### `tests/api/test_canvas_ingestion.py` (5 tests)

`raster.py` produces a valid PNG (signature/IHDR dims/IEND) · finalize creates document+page+revision+job in one flow and OCR completes · second finalized page appends to the same document · already-finalized finalize is a no-op without new artifacts.

Plus the pre-existing 37 tests from Phases 1–2 (auth, profiles/subjects isolation, constraints, idempotency keys, RLS GUC/no-leak, job claim, canvas API/fencing/finalize).

## Manual E2E performed

Through the Vite proxy against PostgreSQL: document create → signed PUT → finalize-upload → 202 with completed OCR (mock); canvas session → strokes → finalize → document_id/revision_id/job_id returned; pages listing shows `ocr_status: completed`.

## Honest gaps

- No concurrency tests for multi-worker claim races on PostgreSQL.
- Reaper logic untested; no beat scheduling.
- No frontend tests for future upload UI.
- RLS behavioral enforcement still untested as restricted role.
- Coverage unmeasured.
