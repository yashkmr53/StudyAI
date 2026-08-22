# Background Jobs — after Phase 5

Runtime unchanged from Phase 3/4 ([`../phase_4/backend/BACKGROUND_JOBS.md`](../../phase_4/backend/BACKGROUND_JOBS.md)). One new job type registered.

## Job registry

| Job name | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure behavior | Status |
|---|---|---|---|---|---|---|---|---|
| `ocr` | finalize-upload / canvas finalize / retry-processing | revision id | DocumentLine* + statuses | 3 attempts, backoff | 600 s | `ocr:{page}:{hash}:{pipeline}` | retryable→dead-letter | ✅ (providers 🔧) |
| `pdf_render` | POST /documents/{id}/pdf (new content) | document id | PDF object + DigitizedDocument | 3 attempts, backoff | 600 s | `pdf:{doc}:{hash32}`; existence short-circuit | retryable→dead-letter | ✅ |
| `index` | OCR success (§47 downstream hook), user-edit revisions, reference ingestion | document id | NoteChunk* w/ embeddings + tsvectors; stale-out superseded chunks | 3 attempts, backoff | 600 s | `index:{doc}:{combined-hash}:{chunker}:{model}` — duplicate keys collapse | retryable→dead-letter; source untouched | ✅ |

## index worker flow

```text
claim → RLS context → build_chunks(document) from CURRENT revisions
      → hash-diff vs active chunks
      → stale-out superseded (retained rows)
      → insert new chunks → embed ONLY those (+ any missing vectors)
      → populate tsvector (PostgreSQL)
```

Re-running with unchanged content is a no-op beyond stats (`created=0 embedded=0`) — the incremental guarantee is covered by `test_index_rerun_is_incremental_not_duplicating`.

## Not yet done

Beat scheduling for the reaper; real-broker integration run; queue-depth metrics.
