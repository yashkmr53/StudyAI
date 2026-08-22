# Background Jobs — after Phase 6

Runtime unchanged (durable rows, atomic claim, backoff/dead-letter, reaper, eager/broker/executor dispatch). One new job type.

## Job registry

| Job name | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure behavior | Status |
|---|---|---|---|---|---|---|---|---|
| `ocr` | finalize-upload / canvas finalize / retry-processing | revision id | DocumentLine* + statuses | 3 attempts, backoff | 600 s | `ocr:{page}:{hash}:{pipeline}` | retryable→dead-letter; source untouched | ✅ (providers 🔧) |
| `pdf_render` | POST /documents/{id}/pdf | document id | PDF + DigitizedDocument | 3 attempts, backoff | 600 s | `pdf:{doc}:{hash32}` + existence short-circuit | retryable→dead-letter | ✅ |
| `index` | OCR success / user edit / reference ingestion | document id | NoteChunk* w/ embeddings+tsvector; stale-out superseded | 3 attempts, backoff | 600 s | `index:{doc}:{combined-hash}:{chunker}:{model}` | retryable→dead-letter | ✅ |
| `enrich` | POST enrich / refresh-ai | document id | EnrichedNote + blocks + citations | 3 attempts, backoff | 600 s | `enrich:{doc}:{descriptor-hash32}[:refresh:N]`; active-note short-circuit | retryable→dead-letter; source + NoteSpace untouched (§52) | ✅ mechanics 🔧 LLM |

## enrich worker flow

```text
claim → RLS context
→ A retrieve: user chunks (≤8) + READY reference chunks (≤6)
→ B draft (schema-validated) → C gap detection → D gap filling → E stitch refs
→ F verify each citation (rules-v1) → supersede old note → persist atomically
```

Failure at any stage marks the job per §19; the canonical document and prior enrichment generations are never mutated.
