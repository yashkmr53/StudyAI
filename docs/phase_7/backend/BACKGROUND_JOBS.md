# Background Jobs — after Phase 7

Runtime unchanged from Phase 5/6. Job registry now includes the learning-feature hooks that run inside the enrich tail (not separate jobs).

## Job registry

| Job name | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure | Status |
|---|---|---|---|---|---|---|---|---|
| `ocr` | finalize-upload / canvas finalize / retry-processing | revision id | lines + statuses | 3 attempts, backoff | 600 s | `ocr:{page}:{hash}:{pipeline}` | retryable→dead-letter | ✅ providers 🔧 |
| `pdf_render` | POST /documents/{id}/pdf | document id | PDF + DigitizedDocument | same | 600 s | `pdf:{doc}:{hash32}` | retryable→dead-letter | ✅ |
| `index` | OCR success / user edit / reference ingestion | document id | chunks+embeddings+tsvector; stale-out; **question stale flags** | same | 600 s | `index:{doc}:{combined-hash}:{chunker}:{model}` | retryable→dead-letter | ✅ |
| `enrich` | POST enrich / refresh-ai | document id | EnrichedNote/Blocks/Citations + **tags** (TaggingService) + **questions** (QuestionGenerationService) | same | 600 s | `enrich:{doc}:{descriptor-hash32}[:refresh:N]`; active-note short-circuit | retryable→dead-letter; source untouched | ✅ mechanics 🔧 LLM |

## Learning hooks inside enrich completion

```text
persist note/blocks/citations
  → TaggingService.extract_for_document(document, generation_job=job)
      · find-or-create stable tags (ADDED logs)
      · link DocumentTags (LINKED logs)
  → QuestionGenerationService.generate_for_document(document)
      · deterministic MCQs bound to revision+hash+key
```

Both steps run inside the enrichment transaction boundary; failures mark the enrich job per §19 without touching source data.

## Not yet done

Beat scheduling for the reaper; real-broker integration run; queue-depth metrics.
