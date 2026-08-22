# Background Jobs — after Phase 4

Runtime unchanged from Phase 3 ([`../phase_3/backend/BACKGROUND_JOBS.md`](../../phase_3/backend/BACKGROUND_JOBS.md)): durable rows, atomic claim, backoff/dead-letter, reaper, eager/broker/DB-polling dispatch. One new registered job type.

## Job registry

| Job name | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure behavior | Status |
|---|---|---|---|---|---|---|---|---|
| `ocr` | finalize-upload / canvas finalize / retry-processing | revision id | DocumentLine* + statuses | 3 attempts, backoff | 600 s | `ocr:{page}:{hash}:{pipeline}` | retryable→dead-letter; source untouched | ✅ (providers 🔧) |
| `pdf_render` | POST /documents/{id}/pdf (new content only) | resource_id = document id | PDF object + DigitizedDocument row | 3 attempts, backoff | 600 s | `pdf:{doc}:{hash32}` unique; completed artifact short-circuits via existence check | retryable→dead-letter; source + prior artifacts untouched | ✅ |

## pdf_render worker flow

```text
claim → RLS context → re-derive layout from CURRENT revisions
      → if artifact already exists: no-op success
      → render_pdf (fpdf2, DejaVu) → store_bytes → INSERT DigitizedDocument
```

Note the double-check inside the handler: two concurrent requests for identical content can share one job key, and whichever renders first creates the row; the loser exits cleanly on the existence check.
