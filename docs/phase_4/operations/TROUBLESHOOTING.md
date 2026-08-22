# Troubleshooting — after Phase 4

Prior guides: [`../phase_3/operations/TROUBLESHOOTING.md`](../operations/TROUBLESHOOTING.md) (uploads, OCR jobs, locks) and earlier. New entries:

## PDF request returns 422 "Page N has no completed revision"

- **Cause:** a page exists without OCR/edit completion (e.g., canvas page finalized but object missing, or upload not finalized).
- **Fix:** complete the flow for that page first (finalize-upload or submit edited lines).

## Generate button stuck on "Rendering…"

- **Diagnose:** `GET /api/v1/jobs/{id}` (id from the 202 response) → check `status`/`last_error`.
- **Causes:** broker-less environment with eager disabled; handler failure (see last_error).
- **Fix:** run `manage.py process_jobs` or restart with dev settings (eager). Failed render jobs reset via re-request — the idempotency key requeues failed states automatically.

## Download URL returns 403

The signed URL expired (300 s TTL) or was tampered with. Re-request `/digitized-documents/{id}/download` to mint a fresh one.

## Non-latin characters missing/garbled in PDF

- **Cause:** vendored DejaVu fonts missing from `backend/assets/fonts` → fallback to latin-1 core fonts.
- **Fix:** restore both `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf`. Note DejaVu has no CJK coverage regardless.

## Old artifact still downloadable after editing

Expected: artifacts are immutable and retained (§27); edits create new revisions ⇒ new artifacts. The UI lists only the latest per document, but old objects remain until a GC policy exists.
