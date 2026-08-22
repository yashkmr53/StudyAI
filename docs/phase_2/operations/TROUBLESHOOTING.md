# Troubleshooting — after Phase 2

Phase 1 guide still applies: [`../phase_1/operations/TROUBLESHOOTING.md`](../../phase_1/operations/TROUBLESHOOTING.md) (Postgres down, missing DB, migrations, superuser-vs-RLS, wrong Python env, port conflicts, PWA cache, 401 loops).

## New in Phase 2

### `409 SESSION_LOCK_LOST` when drawing

- **Symptom:** banner "This sheet is now controlled by another device"; strokes stop syncing.
- **Cause:** another device/tab took over (generation incremented), or the lock expired after ~90 s without heartbeat.
- **Fix:** click **Take over** — the client calls takeover, receives a new generation, and resumes. Pending outbox ops flush automatically afterwards.

### Strokes not leaving the device

- **Diagnose:** DevTools → Application → IndexedDB → `studyai → outbox`: are ops stuck `pending`?
  - If yes with network errors: backend down or proxy misconfigured.
  - If yes with 409s: lock lost — take over.
- **Note:** ops never leave the queue until a valid lock context exists (an active session in this tab).

### Duplicate page number rejected (422)

Two tabs created page N concurrently. Create the next page from one tab only; page numbers are unique per session by design (§66).

### Drawing does nothing on a page

The page is finalized (read-only) or the session lock is lost. Check the page tab for the ✓ marker and the status line under the canvas.

### Two tabs of the same browser fight over the sheet

Both tabs share one `device_id` but each runs its own heartbeat/takeover. Expected single-writer behavior: the last takeover wins; the other tab shows the banner. Use one tab per sheet, or distinct browser profiles for testing multi-device.

### Redis unavailable / OCR failure / LLM failure / PDF generation failure / object storage failure

*(future)* — these components do not exist yet.
