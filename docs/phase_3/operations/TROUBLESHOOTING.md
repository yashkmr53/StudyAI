# Troubleshooting — after Phase 3

Prior guides remain accurate: [`../phase_1/operations/TROUBLESHOOTING.md`](../../phase_1/operations/TROUBLESHOOTING.md), [`../phase_2/operations/TROUBLESHOOTING.md`](../operations/TROUBLESHOOTING.md). New entries:

## Upload returns 403 on the PUT

- **Cause:** signed token expired (300 s TTL), token/key/action mismatch, or clock skew.
- **Fix:** re-create the document (or re-request an upload target) to mint a fresh URL.

## Upload returns 413

- **Cause:** file exceeds `UPLOAD_MAX_BYTES` (10 MB).
- **Fix:** compress/downscale, or raise both `UPLOAD_MAX_BYTES` and `DATA_UPLOAD_MAX_MEMORY_SIZE`.

## Upload returns 422 "Unsupported content type"

Only image/jpeg, image/png, image/webp accepted. Send the right Content-Type header.

## OCR job stuck in QUEUED (non-eager environments)

- **Cause:** no broker (Redis) and nothing polling.
- **Fix:** run `../myenv/bin/python manage.py process_jobs --reap`, or start a Celery worker with a broker. Dev settings default to eager so this shouldn't happen locally.

## Job FAILED_RETRYABLE / FAILED_DEAD_LETTER

- **Diagnose:** `last_error` on `/api/v1/jobs/{id}`; for OCR the common cause is a missing image object.
- **Fix:** `POST /documents/{id}/retry-processing {"page_id"}` — dead-lettered jobs are resettable exactly once per attempt cycle.

## Page shows needs_review

Expected behavior when average OCR confidence < 0.80 (`OCR_REVIEW_THRESHOLD`). Submit corrected lines via `POST /documents/{id}/revisions` with a `lines` array — creates a new immutable revision and clears review state.

## finalize says "No uploaded object found for this page"

The PUT to the signed URL never happened or failed. Re-upload before finalizing.

## Session lock loss during canvas finalize

Unchanged from Phase 2: take over via the editor banner; pending strokes flush afterwards.
