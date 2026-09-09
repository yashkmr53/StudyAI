# Enrichment Pipeline Gap Analysis

## 1. Executive Summary

This report analyzes the StudyAI enrichment pipeline end-to-end, from document upload through OCR, chunking, embedding, retrieval, LLM-based enrichment, citation verification, and downstream learning features (tags, questions).

**Overall Assessment:** The pipeline has a **solid architectural foundation** with durable job state machines, idempotency keys, RLS-ready design, and LangGraph-based orchestration. However, it is **not production-ready** due to critical gaps in real provider integration, RLS enforcement under deployment roles, failure recovery, observability, testing, and security hardening. Many components exist as mocks or stubs, and several failure modes can produce inconsistent or unrecoverable state.

---

## 2. Current Architecture

### 2.1 Repository Structure

```
backend/
├── apps/
│   ├── documents/          # Canonical models (Document, DocumentPage, DocumentPageRevision, DocumentLine)
│   │   ├── models.py
│   │   ├── services.py     # IngestionService, run_ocr_job
│   │   ├── views.py        # DocumentViewSet, upload/finalize/enrich endpoints
│   │   └── note_space.py   # DigitizedDocument PDF pipeline
│   ├── jobs/               # Durable job queue (Job model, dispatch, Celery tasks)
│   │   ├── models.py
│   │   ├── services.py     # get_or_create_job, dispatch_job, execute_job, run_claimed_job
│   │   └── tasks.py        # Celery tasks: process_job_task, reap_stuck_jobs_task, promote_retries_task
│   ├── retrieval/          # Chunking, embedding, hybrid retrieval
│   │   ├── models.py       # NoteChunk
│   │   ├── services.py     # build_chunks, index_document, enqueue_index_job
│   │   └── retrieval.py    # RetrievalService.search (dense + keyword + RRF)
│   ├── ai_classroom/       # Enrichment, tagging, questions
│   │   ├── models.py       # EnrichedNote, EnrichedNoteBlock, CitationBlock, PromptVersion, Tag, DocumentTag
│   │   ├── services.py     # EnrichmentService, EvidenceVerifier
│   │   ├── enrichment_nodes.py  # LangGraph nodes: retrieve, draft, gap_detection, gap_fill, stitch, verify, format
│   │   ├── prompts.py      # PromptVersion seeding, JSON schemas, validate_stage_output
│   │   ├── tagging.py      # Tag extraction, rename
│   │   └── budget.py       # Daily AI budget enforcement
│   ├── chat/               # Chatbot with LangGraph
│   │   ├── models.py       # ChatSession, ChatMessage
│   │   ├── services.py     # ChatService.ask/stream
│   │   └── langgraph_nodes.py  # route, retrieve, generate, verify, retry
│   ├── questions/          # Question generation
│   │   ├── models.py       # Question, QuestionTagLink
│   │   └── services.py     # QuestionGenerationService
│   ├── references/         # ReferenceBook pipeline
│   │   └── models.py       # ReferenceBook, ReferenceBookChapter
│   ├── audit/              # AuditLog, ProviderCallLog
│   │   ├── models.py
│   │   └── services.py
│   └── evaluation/         # EvalRun, runner (retrieval/citation/agent metrics)
│       ├── models.py
│       └── runner.py
├── providers/              # Provider abstraction layer
│   ├── base.py             # Protocols: OCRProvider, LLMProvider, EmbeddingProvider, ObjectStorageProvider
│   ├── registry.py         # get_ocr_provider, get_llm_provider, get_embedding_provider, get_object_storage
│   ├── ocr/                # MockOCRProvider, OCRChainProvider
│   ├── llm/                # MockLLMProvider, LLMChainProvider, FailingLLMProvider
│   ├── embeddings/         # HashingEmbeddingProvider (deterministic lexical hash)
│   └── storage/            # LocalObjectStorage
├── ai/
│   ├── langgraph/          # LangGraph workflow definitions
│   │   ├── graphs/         # enrichment_graph.py, chat_graph.py, question_generation_graph.py
│   │   ├── nodes/          # agent_nodes.py, verification_nodes.py
│   │   └── state/          # EnrichmentState, ChatState, VerificationState
│   ├── prompts/            # Prompt templates
│   ├── schemas/            # Pydantic schemas for LLM structured output
│   └── tracing/            # LangSmith tracing decorators
├── shared/
│   ├── database/
│   │   ├── rls.py          # Transaction-local RLS context
│   │   └── middleware.py
│   ├── idempotency/
│   │   └── keys.py         # ocr_key, embedding_key, enrichment_key
│   ├── exceptions/         # APIError hierarchy, exception_handler
│   └── throttles.py        # Rate throttles
└── config/
    ├── celery.py           # Beat schedule (reap, promote, backup, budget reset)
    └── settings/           # Django settings (dev, prod)
```

### 2.2 Data Flow

```text
User uploads image/canvas page
  ↓
POST /api/v1/documents → Document + DocumentPage created
  ↓
Client uploads to object storage (signed URL)
  ↓
POST /api/v1/documents/{id}/revisions (or finalize-upload)
  ↓
IngestionService.finalize_upload()
  → validate object exists
  → compute content_hash
  → create DocumentPageRevision (status=PENDING)
  → enqueue_ocr_job() → Job(idempotency_key=ocr:{page_id}:{hash}:{pipeline_version})
  ↓
Celery worker: process_job_task → execute_job → claim(RUNNING)
  ↓
run_ocr_job()
  → idempotency check (already COMPLETED + has lines → skip)
  → OCRChainProvider.recognize() [primary → fallback]
  → transaction.atomic():
      delete old DocumentLines
      bulk_create new DocumentLines
      update revision status (COMPLETED or NEEDS_REVIEW)
      update page status
  → enqueue_index_job(page.document)
  ↓
run_index_job()
  → build_chunks() [page-aware greedy packing]
  → index_document():
      mark stale chunks
      create new NoteChunks
      embed new chunks via provider.embed()
      populate tsvector
      mark EnrichedNote.ai_stale=True
  ↓
User triggers enrichment: POST /documents/{id}/enrich
  ↓
EnrichmentService.enqueue_enrichment()
  → budget check
  → coalescing window check
  → create Job(job_type="enrich", idempotency_key=enrich:{doc_id}:{descriptor[:32]})
  → dispatch_job()
  ↓
run_enrichment_job()
  → invoke_enrichment_graph(initial_state)
    → retrieve_chunks_node: load up to 8 user chunks + 6 random reference chunks
    → draft_node: LLM.generate_structured(enrichment_draft)
    → gap_detection_node: LLM.generate_structured(gap_detection)
    → [conditional] gap_fill_node: LLM.generate_structured(gap_filling)
    → citation_stitch_node: map source_chunk_ids → refs
    → evidence_verification_node: EvidenceVerifier.verify() per block
    → format_output_node
  → transaction.atomic():
      supersede old EnrichedNote
      create new EnrichedNote
      create EnrichedNoteBlocks + CitationBlocks
  → TaggingService.extract_for_document()
  → QuestionGenerationService.generate_for_document()
```

---

## 3. Actual End-to-End Data Flow

### 3.1 Upload → OCR

| Stage | Entry Point | Trigger | Input | Output | DB Writes | External |
|-------|------------|---------|-------|--------|-----------|----------|
| Create document | `DocumentViewSet.create()` | API POST | user, profile, source_type | Document + Page + upload URL | Document, DocumentPage | Object storage (signed URL) |
| Upload | Client PUT | Direct to storage | binary image | object stored | none | S3/MinIO/Local |
| Finalize | `DocumentViewSet.create_revision()` or `FinalizeUploadView` | API POST | page_id | Revision + Job | DocumentPageRevision, Job | none |
| OCR worker | `process_job_task` → `execute_job` → `run_ocr_job` | Celery | Job PK | DocumentLines + status | DocumentLine (bulk), Revision, Page | OCR provider |

### 3.2 OCR → Indexing

| Stage | Entry Point | Trigger | Input | Output | DB Writes | External |
|-------|------------|---------|-------|--------|-----------|----------|
| Enqueue index | `run_ocr_job` calls `enqueue_index_job` | Post-OCR hook | Document | Job | Job | none |
| Index worker | `process_job_task` → `run_index_job` | Celery | Job PK | Chunks + embeddings | NoteChunk, EnrichedNote.ai_stale | Embedding provider |

### 3.3 Index → Enrichment

| Stage | Entry Point | Trigger | Input | Output | DB Writes | External |
|-------|------------|---------|-------|--------|-----------|----------|
| Enqueue enrich | `DocumentViewSet.enrich` | API POST | document_id | Job | Job | none |
| Enrich worker | `process_job_task` → `run_enrichment_job` | Celery | Job PK | EnrichedNote + Blocks + Citations | EnrichedNote, EnrichedNoteBlock, CitationBlock, DocumentTag, TagChangeLog, Question | LLM provider |

---

## 4. Intended Behavior

### 4.1 Confirmed Behavior (supported by code/tests/docs)

- **Canonical document model**: Document → Page → Revision → Line is immutable and reproducible.
- **OCR idempotency**: `ocr:{page_id}:{content_hash}:{pipeline_version}` prevents duplicate OCR.
- **Job state machine**: QUEUED → RUNNING → SUCCEEDED / FAILED_RETRYABLE → QUEUED / FAILED_DEAD_LETTER. Atomic claim via conditional update.
- **Reaper**: `reap_stuck_jobs` requeues RUNNING jobs past timeout (default 600s).
- **Retry backoff**: Exponential with jitter; max attempts configurable (default 3).
- **Chunking**: Page-aware greedy packing with overlap; deterministic given same input.
- **Incremental indexing**: New/changed chunks embedded; stale chunks marked `stale=True`; superseded questions marked stale.
- **Enrichment pipeline**: A→F stages (Retrieve→Draft→GapDetect→GapFill→Stitch→Verify) via LangGraph.
- **Schema validation**: `validate_stage_output` enforces JSON schema after each LLM node.
- **Evidence verification**: Rule-based lexical support with configurable thresholds (supported≥0.60, partial≥0.30).
- **Budget enforcement**: Daily generation count per profile; 429 when exhausted.
- **Provider call logging**: `ProviderCallLog` records latency, success, tokens, cost.
- **RLS scaffolding**: `profile_scoped_transaction` sets `SET LOCAL app.current_profile_id`.

### 4.2 Inferred Behavior (intended but not fully specified)

- Real LLM/OCR/embedding providers are expected to replace mocks in production.
- Enrichment coalescing window is tunable but change-magnitude threshold is a placeholder.
- Prompt injection directives are present in `LLMChainProvider` but prompts themselves don't wrap evidence in `<source>` tags as §72 suggests.
- Data-minimization redaction is implemented in `LLMChainProvider._sanitize_for_provider` but not consistently applied to all provider inputs (e.g., OCR image content not redacted, though it's binary).
- Reference-book chunks should only be retrieved when book status is READY (enforced in `RetrievalService.search`).
- `PromptVersion` registry is seeded idempotently but prompt versions in `EnrichedNote` are stored as `";".join(QUALIFIED.values())` rather than per-stage versions.

### 4.3 Missing Specification

- No golden evaluation dataset exists (F1).
- Evidence verifier thresholds are arbitrary defaults (F2).
- No documented RPO/RTO for backups.
- No explicit handling for LangGraph node failures mid-execution.
- No specification for what happens when `EnrichedNote` creation fails after LLM calls succeed (partial state).
- No specification for concurrent enrichment requests for the same document.

---

## 5. State Machine

### 5.1 Document/Revision States

```
DocumentPageRevision.ocr_status:
  PENDING → PROCESSING → COMPLETED
                         → NEEDS_REVIEW
                         → FAILED

Job.status:
  QUEUED → RUNNING → SUCCEEDED
                   → FAILED_RETRYABLE → QUEUED (after backoff)
                   → FAILED_DEAD_LETTER (terminal)
                   → CANCELLING → CANCELLED
```

### 5.2 Enrichment-Specific States

There is **no explicit enrichment state machine** beyond the generic Job states. The `EnrichedNote` model uses:
- `ai_stale=True`: set when source chunks change (in `index_document`)
- `superseded=True`: set when a new enrichment is created

### 5.3 State Machine Gaps

| Issue | Severity | Evidence |
|-------|----------|----------|
| No PARTIALLY_COMPLETED state for enrichment | Medium | `EnrichedNote` is created atomically, but if tagging/question generation fails after note creation, the note exists without downstream artifacts |
| FAILED_DEAD_LETTER has no automatic alerting | Medium | Job dead-letters silently; no notification to user |
| RUNNING jobs reaped by timeout lose their work if transaction already committed | Medium | `reap_stuck_jobs` marks retryable but partial DB writes may have occurred |
| Enrichment job can be created while index job is still running | Low | `enqueue_enrichment` doesn't check if `index` job is pending; chunks may be incomplete |

---

## 6. Functional Gaps

### 6.1 Input Handling

| Gap | Severity | Evidence |
|-----|----------|----------|
| No file type/size validation on upload | Medium | `DocumentCreateSerializer` doesn't validate content_type or file size |
| Empty/malformed documents not rejected early | Medium | `finalize_upload` only checks `image_ref` exists in storage; no image validation |
| Duplicate uploads create duplicate Documents | Low | No deduplication at upload time; idempotency is at OCR job level only |
| Partial uploads not handled | Medium | No multipart upload support; single PUT expected |

### 6.2 Extraction (OCR)

| Gap | Severity | Evidence |
|-----|----------|----------|
| MockOCRProvider only; no real OCR in production | CRITICAL | `providers/ocr/mock.py` — deterministic fake lines; `registry.py` defaults to `mock,mock` |
| No OCR output validation | High | `run_ocr_job` trusts provider output; no check for empty lines, malformed bbox, or extreme confidence values |
| Low-confidence pages flagged NEEDS_REVIEW but no user workflow | Medium | `DocumentPage.needs_review` exists; no dedicated review UI endpoint beyond `create_user_revision` |
| OCR fallback never triggered in mock mode | Low | `OCRChainProvider` falls back only on exception; mock doesn't fail |

### 6.3 Chunking

| Gap | Severity | Evidence |
|-----|----------|----------|
| Chunk overlap is line-based, not word-based | Low | `flush()` carries last 3 lines, not last N words; overlap_words setting is computed but not precisely enforced |
| Empty chunks possible if all lines are whitespace | Low | `build_chunks` filters nothing; empty lines produce empty chunks |
| Random reference chunk selection (`order_by("?")`) is non-deterministic | Medium | `retrieve_chunks_node` uses `.order_by("?")[:6]`; same document can produce different enrichment on repeated runs |
| No chunk size upper bound | Low | Target is 120 words; a single long line exceeds it |

### 6.4 Enrichment

| Gap | Severity | Evidence |
|-----|----------|----------|
| Change magnitude is a hardcoded placeholder (0.5) | HIGH | `_compute_change_magnitude` returns `0.5` with comment "Placeholder — in production, compute actual cosine similarity" |
| Coalescing window logic is flawed: pending job returned even if document has changed | HIGH | `enqueue_enrichment` returns existing pending job if `magnitude <= threshold`, but magnitude is always 0.5 (always below 0.15? No, 0.5 > 0.15, so coalescing never triggers) |
| No timeout on LLM calls within LangGraph nodes | HIGH | `draft_node`, `gap_detection_node`, `gap_fill_node` call `llm.generate_structured()` with no timeout; a hanging provider blocks the worker indefinitely |
| No retry within a single enrichment job | HIGH | If `draft_node` fails, the entire enrichment job fails and retries from the start (re-running retrieve, draft, etc.) |
| Schema validation errors crash the node | HIGH | `validate_stage_output` raises `ValidationError`; uncaught in node → job fails → dead-letter after 3 attempts |
| Prompt injection directives prepended but evidence not wrapped in `<source>` tags as §72 specifies | MEDIUM | `LLMChainProvider` prepends directive but `evidence_payload` is raw JSON, not wrapped in source blocks |
| Reference chunks retrieved randomly, not by relevance to gaps | MEDIUM | `retrieve_chunks_node` loads 6 random reference chunks; gap_fill uses `evidence_payload` which includes all reference chunks, not gap-specific ones |
| No handling for LLM returning empty blocks | MEDIUM | Schema requires `blocks` array but doesn't enforce minimum length; empty enrichment creates EnrichedNote with no blocks |
| `_descriptor` includes `QUALIFIED.values()` which is all prompt versions, not per-stage | LOW | `_descriptor` hashes `prompt_versions = ",".join(sorted(QUALIFIED.values()))`; changing any prompt version invalidates all enrichments |

### 6.5 Embeddings

| Gap | Severity | Evidence |
|-----|----------|----------|
| HashingEmbeddingProvider is lexical-grade only | HIGH | `providers/embeddings/hashing.py` — MD5-based feature hash; no semantic similarity |
| Embedding dimension is hardcoded 384 for non-pgvector backends | LOW | `AdaptiveVectorField.db_type` returns "text" for SQLite; no dimension validation |
| No batching for embedding calls | MEDIUM | `provider.embed([c.content for c in embeddable])` sends all at once; no chunking for large batches |
| Failed embeddings leave chunks unindexed with no retry | MEDIUM | `index_document` catches no exceptions from `provider.embed()`; if it fails, chunks have `embedding=NULL` and are not retried |

### 6.6 Storage/Indexing

| Gap | Severity | Evidence |
|-----|----------|----------|
| Stale chunk resurrection logic is flawed | HIGH | `index_document` does `obj.stale = False; obj.save(update_fields=("stale",))` but doesn't re-embed resurrected chunks if their embedding is NULL |
| Superseded questions marked stale but not linked to new chunks | MEDIUM | `index_document` marks `Question.stale=True` for superseded chunks, but no mechanism generates new questions for new chunks |
| No orphan cleanup | MEDIUM | DigitizedDocuments, old revisions, stale chunks, dead-letter jobs accumulate indefinitely |
| tsvector population uses `SearchVector("content", config="english")` in Python loop | LOW | `index_document` iterates all chunks with null tsvector; should use `update(tsvector_content=...)` in bulk |

---

## 7. Reliability & Failure Gaps

### 7.1 External Dependency Failures

| Dependency | Failure Mode | Current Handling | Gap |
|------------|-------------|------------------|-----|
| OCR provider | All providers fail | `OCRChainProvider` raises `ProviderError` → job dead-letters | No fallback to mark page as FAILED with retry later |
| LLM provider | Timeout/hang | No timeout; blocks worker indefinitely | Worker stuck; reaper requeues after 600s but LLM call may still be running |
| LLM provider | All providers fail | `LLMChainProvider` raises `ProviderError` → job dead-letters | No graceful degradation; enrichment unavailable |
| Embedding provider | Failure | No try/except in `index_document` | Transaction rolls back but job succeeds? Actually `run_index_job` doesn't catch exceptions |
| Object storage | Object missing | `run_ocr_job` raises ValidationError → job retryable | Good |
| Object storage | Connection failure | No connection retry; `storage.exists()` may hang | No timeout on storage calls |
| Database | Connection lost mid-transaction | Django handles; partial writes rolled back | Job retried; idempotency prevents duplicates |

### 7.2 Partial Failure Scenarios

| Scenario | Current Behavior | Gap |
|----------|-----------------|-----|
| OCR succeeds, index job enqueued, index job fails | OCR revision stays COMPLETED; index job retries | Good |
| LLM draft succeeds, gap_detection fails | Job fails; retry re-runs entire graph from retrieve | Wastes LLM calls; no intermediate state persistence |
| EnrichedNote created, tagging fails | Note exists; no tags; no questions | Inconsistent state; user sees enrichment but no tags/questions |
| Embedding succeeds, tsvector update fails | Chunk has embedding but no keyword index | Retrieval degrades to dense-only for that chunk |

---

## 8. Idempotency & Concurrency Gaps

### 8.1 Idempotency

| Operation | Idempotency Key | Mechanism | Gap |
|-----------|----------------|-----------|-----|
| OCR | `ocr:{page_id}:{hash}:{pipeline_version}` | Job unique constraint | Good |
| Index | `index:{doc_id}:{revision_hash[:32]}:{chunker_version}:{model_version}` | Job unique constraint | Good |
| Enrichment | `enrich:{doc_id}:{descriptor[:32]}` | Job unique constraint | Good, but coalescing logic broken |
| Chunk creation | `(revision_id, content_hash, chunk_index)` unique constraint | DB constraint | Good |
| EnrichedNote | `(document, content_hash)` unique constraint when `superseded=False` | DB constraint | Good |

### 8.2 Race Conditions

| Race | Current Protection | Gap |
|------|-------------------|-----|
| Two workers claim same job | `job.claim()` uses atomic conditional update | Good |
| Two index jobs for same document | `enqueue_index_job` idempotency key | Good |
| Two enrich jobs for same document | `enqueue_enrichment` idempotency key + coalescing window | Coalescing logic broken (always creates new job because magnitude=0.5 > threshold=0.15) |
| Concurrent user edits to same page | No optimistic locking; `_create_revision_locked` reads last revision number without lock | Two edits can create same revision_number; second overwrites first |
| Two enrichment requests while one is running | Returns existing pending job | Good |

### 8.3 Duplicate Processing Risks

| Risk | Likelihood | Impact | Evidence |
|------|-----------|--------|----------|
| Duplicate chunks if index job crashes after bulk_create but before embedding | Low | Duplicate chunks with same content_hash | `NoteChunk.objects.get_or_create` prevents duplicates |
| Duplicate LLM calls if job retries after draft succeeds | High | Wasted LLM spend; same result | No intermediate state persistence in LangGraph |
| Duplicate EnrichedNotes if job retries after supersede | Low | Old note resurrected | `transaction.atomic` + supersede inside transaction prevents this |
| Duplicate tags on retry | Low | TagChangeLog spam | `Tag.objects.get_or_create` prevents duplicates |

---

## 9. Data Consistency Gaps

| Scenario | Result | Gap |
|----------|--------|-----|
| DB write succeeds, LLM call fails | Job retries; no partial state | Good — LLM outside transaction |
| LLM succeeds, DB write fails | Job retries; LLM called again | Wasted LLM spend; no caching of LLM results |
| Embedding succeeds, indexing fails | Chunk has embedding but not in tsvector | Partial retrieval capability |
| Task crashes halfway | Transaction rolls back; job retries | Good |
| Worker killed after commit but before `mark_succeeded` | Reaper requeues; idempotency prevents duplicates | Good |
| Enrichment fails after Note creation | Note exists without blocks/citations | No cleanup of partial EnrichedNote |

---

## 10. Scalability & Performance Gaps

| Issue | Impact | Evidence |
|-------|--------|----------|
| `order_by("?")` on NoteChunk for reference chunks | Full table scan + sort; O(n) on large chunk sets | `retrieve_chunks_node` line 34 |
| `provider.embed([c.content for c in embeddable])` no batching | Memory spike for large documents | `index_document` line 230 |
| `SearchVector("content", config="english")` in Python loop | N+1 queries for tsvector population | `index_document` lines 242-246 |
| No connection pooling configured | Worker exhaustion under load | Django default; no `CONN_MAX_AGE` in settings |
| `promote_due_retries` and `reap_stuck_jobs` scan full Job table | Slow with many jobs | No index on `next_retry_at` or `started_at` |
| `_compute_change_magnitude` queries previous job for every enrichment | N+1 on Job table | `EnrichmentService._compute_change_magnitude` |

---

## 11. Security Gaps

| Issue | Severity | Evidence |
|-----|----------|----------|
| RLS not enforced under deployment role | CRITICAL | Architecture §3 says app connects as superuser; PostgreSQL exempts superusers from RLS. Restricted role never wired into prod config. |
| CORS not configured | HIGH | `CORS_ALLOWED_ORIGINS` absent; works only because SPA is same-origin behind nginx |
| CSRF_TRUSTED_ORIGINS not configured | HIGH | Missing for API endpoints that accept cookies |
| Prompt injection: evidence not wrapped in `<source>` tags | HIGH | §72 specifies wrapping; `evidence_payload` is raw JSON without source/sanitization wrappers |
| Signed URL TTL hardcoded to 300s | MEDIUM | `SIGNED_URL_TTL_SECONDS=300`; no per-user or per-resource variation |
| No file type validation on upload | MEDIUM | `DocumentCreateSerializer` accepts any content_type |
| API keys in .env not rotated | MEDIUM | Static keys; no rotation mechanism |
| `ProviderCallLog` may log sensitive data in `metadata` | LOW | `metadata={"redactions_count": ...}` is safe, but future extensions could leak content |
| No tenant isolation checks in retrieval | HIGH | `RetrievalService.search` filters by `profile_id__in=profile_ids` but relies on application layer; RLS should enforce at DB level |
| Chat messages store user content without sanitization | MEDIUM | `ChatMessage.content` stored as-is; XSS risk in frontend |

---

## 12. Observability Gaps

| Gap | Severity | Evidence |
|-----|----------|----------|
| No structured logs with correlation IDs in enrichment nodes | MEDIUM | `enrichment_nodes.py` uses `logger.info` but no request_id propagation |
| No stage-level timing in enrichment | MEDIUM | Only `time.monotonic()` in nodes; not aggregated |
| No dead-letter alerting | MEDIUM | Job dead-letters silently; user sees nothing |
| ProviderCallLog lacks prompt/response content | LOW | Only metadata; no content for debugging |
| No metrics for enrichment success rate, LLM latency, token usage | MEDIUM | `ProviderCallLog` has rows but no aggregation/alerting |
| No traceback in Job.last_error beyond 4000 chars | LOW | `last_error = error[:4000]` truncates stack traces |
| LangSmith tracing disabled by default | LOW | `LANGSMITH_TRACING=false` in .env.example |

---

## 13. Configuration Gaps

| Issue | Severity | Evidence |
|-----|----------|----------|
| `ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15` is meaningless since magnitude is always 0.5 | HIGH | `_compute_change_magnitude` returns hardcoded 0.5 |
| `CHUNK_OVERLAP_WORDS=30` is computed but not precisely enforced | LOW | `build_chunks` uses line-based carry, not word-based overlap |
| `MAX_PROVIDER_INPUT_CHARS=8000` applies only to LLM, not embeddings | MEDIUM | Embedding provider receives full chunk content; no truncation |
| `EMBEDDING_DIMENSIONS=384` is hardcoded for hashing provider | LOW | Real providers may need different dimensions |
| `JOBS_TIMEOUT_SECONDS=600` may be too short for LLM calls | MEDIUM | Real LLM can take >10 minutes; reaper requeues active job |
| `CELERY_TASK_ALWAYS_EAGER` runs jobs inline | MEDIUM | Dev/test only; must be False in prod |
| No `CELERY_BROKER_URL` validation on startup | LOW | If Redis is down, jobs queue in DB but never process |

---

## 14. Testing Gaps

| Area | Existing Coverage | Missing Coverage | Risk |
|------|-------------------|-----------------|------|
| Extraction | MockOCRProvider tested | No real OCR provider tests; no malformed image tests | HIGH |
| Chunking | None | No unit tests for `build_chunks` edge cases (empty doc, single line, huge line) | HIGH |
| Indexing | None | No tests for incremental indexing, stale resurrection, orphan cleanup | HIGH |
| Enrichment | Node unit tests (mocked LLM) | No end-to-end enrichment job test; no failure injection; no concurrent enrichment test | CRITICAL |
| Embeddings | None | No tests for embedding provider switching, dimension mismatches, batch failures | HIGH |
| Retry | Job retry tested in unit tests | No integration test for LLM timeout → retry → dead-letter | HIGH |
| Idempotency | OCR idempotency via key | No test for concurrent enrichment requests; no test for index job during edit | CRITICAL |
| Failure recovery | Reaper tested | No test for worker crash mid-transaction; no test for partial LLM failure | HIGH |
| Concurrency | None | No test for two workers processing same document; no test for concurrent user edits | HIGH |
| Security | None | No RLS test for enrichment worker context; no cross-user data leak test | HIGH |
| Observability | None | No test for ProviderCallLog writes; no test for log correlation | MEDIUM |

---

## 15. Documentation Gaps

| Gap | Severity |
|-----|----------|
| No runbook for enrichment failure recovery | HIGH |
| No runbook for dead-letter job handling | HIGH |
| No runbook for RLS role setup in production | HIGH |
| No documented procedure for golden dataset authoring | MEDIUM |
| No documented procedure for verifier calibration | MEDIUM |
| No architecture diagram showing LangGraph node dependencies | MEDIUM |
| No API documentation for enrichment endpoints | MEDIUM |
| No description of prompt injection defense strategy | MEDIUM |
| No data retention policy documentation | LOW |

---

## 16. Gap Matrix

| ID | Area | Current Behavior | Expected Behavior | Gap | Severity | Evidence | Recommended Fix |
|----|------|------------------|-------------------|-----|----------|----------|----------------|
| G1 | OCR Provider | Only MockOCRProvider | Real OCR provider (Tesseract/Google) | No real text extraction | CRITICAL | `providers/ocr/mock.py`, `registry.py` defaults to mock | Implement production OCR provider; add health check |
| G2 | LLM Provider | Only MockLLMProvider | Real LLM provider (OpenAI/Ollama) | No real enrichment | CRITICAL | `providers/llm/mock.py`, `registry.py` defaults to mock | Implement production LLM provider; add timeout/retry |
| G3 | RLS Enforcement | Superuser connection bypasses RLS | Restricted app role with RLS enforced | Cross-user data leak possible | CRITICAL | `docker-compose.yml` connects as superuser; `shared/database/rls.py` exists but not wired | Create restricted DB role; update Django DATABASES; verify with probe |
| G4 | Embeddings | HashingEmbeddingProvider (lexical) | Semantic embeddings (sentence-transformers) | Poor retrieval quality | HIGH | `providers/embeddings/hashing.py` | Switch to `SentenceTransformerEmbeddingProvider`; backfill embeddings |
| G5 | Change Magnitude | Hardcoded 0.5 placeholder | Actual cosine similarity between old/new chunks | Coalescing window broken | HIGH | `EnrichmentService._compute_change_magnitude` returns 0.5 | Store previous descriptor hash; compute real magnitude |
| G6 | LLM Timeout | No timeout on `generate_structured` | Configurable timeout per stage | Worker hangs indefinitely | HIGH | `enrichment_nodes.py` lines 69, 105, 143 | Add timeout parameter; use `asyncio.wait_for` or provider-level timeout |
| G7 | Enrichment Retry | Retries entire graph from start | Resume from failed node | Wasted LLM spend; longer latency | HIGH | `run_enrichment_job` calls `invoke_enrichment_graph` with no checkpointing | Persist intermediate state to DB; resume from failed node |
| G8 | Partial Enrichment Failure | EnrichedNote created without blocks/citations if tagging fails | Atomic creation of note + blocks + citations + tags | Inconsistent state | HIGH | `run_enrichment_job` lines 262-306; tagging outside transaction | Wrap tagging + question generation in same transaction or compensate |
| G9 | Embedding Failure | No error handling; transaction rolls back but job status unclear | Graceful degradation with retry | Chunks stuck without embeddings | HIGH | `index_document` line 230-235 | Add try/except around `provider.embed()`; mark failed chunks for retry |
| G10 | Reference Chunk Retrieval | Random 6 reference chunks | Relevance-based retrieval for gaps | Low-quality gap filling | MEDIUM | `retrieve_chunks_node` line 34 `order_by("?")` | Retrieve reference chunks based on gap topics, not random |
| G11 | Prompt Injection Defense | Directive prepended but evidence not wrapped | Evidence wrapped in `<source>` tags as §72 specifies | Potential prompt injection | HIGH | `LLMChainProvider` line 102-103; `enrichment_nodes.py` passes raw JSON | Wrap evidence in XML-like source blocks; sanitize LLM output |
| G12 | Data Minimization | Redaction in LLMChainProvider only | Consistent redaction before all provider calls | PII leakage to providers | MEDIUM | `providers/llm/chain.py` `_sanitize_for_provider`; no similar logic in OCR or embeddings | Extract redaction to shared utility; apply to all provider inputs |
| G13 | Coalescing Logic | Always creates new job because magnitude=0.5 > threshold=0.15 | Coalescing window prevents redundant jobs | Wasted LLM spend | HIGH | `EnrichmentService.enqueue_enrichment` lines 189-205 | Fix magnitude computation; test coalescing |
| G14 | Stale Chunk Resurrection | Resurrects chunk without re-embedding | Re-embed resurrected chunks if embedding is NULL | Incomplete index | HIGH | `index_document` lines 209-211 | Check embedding after resurrection; embed if NULL |
| G15 | Concurrency - User Edit | No optimistic locking on page revision | Detect concurrent edits with 409 | Lost updates | MEDIUM | `_create_revision_locked` reads last revision without lock | Add `version` field; use `select_for_update` |
| G16 | Test Coverage - Enrichment E2E | Node unit tests only | End-to-end job execution test | Unverified integration | CRITICAL | `tests/unit/test_enrichment_graph.py` mocks everything | Add integration test with real DB and mock providers |
| G17 | Test Coverage - Idempotency | OCR key tested | Concurrent enrichment, index-during-edit | Race conditions | CRITICAL | No tests for concurrent jobs | Add concurrent job tests with threading |
| G18 | Observability - Correlation IDs | Request ID middleware exists | Correlation ID in all enrichment logs | Hard to debug failures | MEDIUM | `shared/observability/request_id.py`; not used in workers | Propagate request_id from job to all log calls |
| G19 | Observability - Metrics | ProviderCallLog rows | Aggregated metrics (success rate, latency, token usage) | No visibility | MEDIUM | `apps/audit/models.py`; no aggregation | Add Prometheus metrics or daily summary job |
| G20 | Security - CORS | Absent | Configured CORS origins | CSRF risk | HIGH | `shared/exceptions/handlers.py` no CORS config | Add `django-cors-headers`; configure `CORS_ALLOWED_ORIGINS` |
| G21 | Security - CSRF Trusted Origins | Absent | Configured for API | CSRF risk | HIGH | `.env.example` has placeholder | Add `CSRF_TRUSTED_ORIGINS` |
| G22 | Backup Automation | Commands exist; no scheduler | Automated daily backups | Data loss risk | HIGH | `apps/audit/tasks.py` daily_backup; `celery.py` has schedule but no beat service in compose | Add Celery Beat service to docker-compose; test restore |
| G23 | Golden Dataset | Empty | 30-50 labeled cases | No evaluation baseline | MEDIUM | `apps/evaluation/runner.py` exists; no datasets | Author golden dataset; run evaluation in CI |
| G24 | Verifier Calibration | Arbitrary thresholds (0.60, 0.30) | Calibrated against labeled data | Unreliable citation status | MEDIUM | `EvidenceVerifier._supported_threshold` | Run evaluation; adjust thresholds; version verifier |
| G25 | Object Storage GC | No cleanup | Remove orphaned objects | Storage cost leak | MEDIUM | `providers/storage/local.py` no GC | Implement GC job; track object references |
| G26 | Profile Deletion | No cascade/anonymization | GDPR-compliant deletion | Privacy violation | MEDIUM | No `apps/profiles/signals.py` | Implement post_delete signal; anonymize or delete profile-owned data |

---

## 17. Critical Findings

### Finding 1: No Real OCR or LLM Providers (G1, G2)

**Problem:** The entire enrichment pipeline depends on `MockOCRProvider` and `MockLLMProvider`. These produce deterministic fake outputs. The pipeline is **non-functional for real users**.

**Why it matters:** Without real providers, the system cannot process actual handwritten notes or generate real enrichment. It is a demo, not a production system.

**Files/components affected:** `providers/ocr/`, `providers/llm/`, `registry.py`, `docker-compose.yml`

**Recommended approach:**
1. Implement production OCR provider (e.g., Tesseract for local, Google Vision for cloud).
2. Implement production LLM provider (OpenAI, Anthropic, or Ollama for local).
3. Add health check endpoints for provider availability.
4. Add circuit breaker pattern to fail fast when providers are down.

**Dependencies:** Vendor selection, API keys, model deployment.

**Tests required:** Integration tests with real providers in staging; failure injection tests.

---

### Finding 2: RLS Not Enforced Under Deployment Role (G3)

**Problem:** The application connects to PostgreSQL as a superuser. PostgreSQL exempts superusers from RLS policies. The `profile_scoped_transaction` context is set but **not enforced** at the DB level.

**Why it matters:** A bug or SQL injection could expose all users' data across profiles. Multi-tenant isolation is compromised.

**Files/components affected:** `docker-compose.yml`, `config/settings/`, `shared/database/rls.py`, migrations

**Recommended approach:**
1. Create a restricted application role with `SET ROLE` capability.
2. Update Django `DATABASES` to connect as restricted role.
3. Run RLS behavioral probe in CI.
4. Document role setup in runbook.

**Dependencies:** DBA approval for role separation.

**Tests required:** RLS enforcement test that verifies cross-profile access is blocked at DB level.

---

### Finding 3: Enrichment Retry Wastes LLM Calls (G7)

**Problem:** If a LangGraph node fails mid-execution, the entire graph is re-invoked from the start on retry. All previous LLM calls are repeated.

**Why it matters:** LLM calls are expensive (in time and money). For a 4-node graph with 3 LLM calls, a failure in node 4 wastes 75% of the work.

**Files/components affected:** `apps/ai_classroom/services.py` `run_enrichment_job`, `ai/langgraph/graphs/enrichment_graph.py`

**Recommended approach:**
1. Add checkpointing to LangGraph state: persist state after each node to a `JobExecutionState` model.
2. On retry, load last checkpoint and resume from next node.
3. Alternatively, cache LLM results by `(prompt_name, prompt_version, evidence_hash)`.

**Dependencies:** LangGraph checkpointing support or custom state persistence.

**Tests required:** Failure injection test that verifies resume from checkpoint.

---

### Finding 4: Change Magnitude Placeholder Breaks Coalescing (G5, G13)

**Problem:** `_compute_change_magnitude` returns hardcoded 0.5, which is always above the threshold of 0.15. This means the enrichment coalescing window **never triggers**, and every edit creates a new enrichment job.

**Why it matters:** Users who make minor edits trigger redundant, expensive enrichment jobs.

**Files/components affected:** `apps/ai_classroom/services.py` `EnrichmentService._compute_change_magnitude`

**Recommended approach:**
1. Store previous descriptor hash on `EnrichedNote` or `Job`.
2. Compute actual cosine similarity between current and previous chunk embeddings (or content hashes as proxy).
3. Use content-hash Jaccard similarity for simplicity until embeddings are stable.

**Tests required:** Test that coalescing prevents redundant jobs when changes are minor.

---

### Finding 5: No LLM Timeout (G6)

**Problem:** `llm.generate_structured()` has no timeout. A hanging or extremely slow LLM provider blocks the Celery worker indefinitely.

**Why it matters:** A single slow provider can exhaust the worker pool, causing all jobs to stall.

**Files/components affected:** `apps/ai_classroom/enrichment_nodes.py`, `apps/chat/langgraph_nodes.py`, `providers/llm/chain.py`

**Recommended approach:**
1. Add `timeout` parameter to `LLMProvider.generate_structured` protocol.
2. Pass timeout from settings (e.g., `LLM_TIMEOUT_SECONDS=120`).
3. In `LLMChainProvider`, wrap call in `asyncio.wait_for` or use provider SDK timeouts.
4. On timeout, treat as provider failure and try fallback.

**Dependencies:** Provider SDK timeout support.

**Tests required:** Test that slow LLM responses are timed out and fallback is triggered.

---

### Finding 6: Partial Enrichment Failure Leaves Inconsistent State (G8)

**Problem:** `run_enrichment_job` creates the `EnrichedNote` in a transaction, but `TaggingService.extract_for_document` and `QuestionGenerationService.generate_for_document` run **outside** that transaction. If tagging fails, the note exists without tags or questions.

**Why it matters:** Users see enrichment without associated learning artifacts. The system is in an inconsistent state.

**Files/components affected:** `apps/ai_classroom/services.py` `run_enrichment_job`

**Recommended approach:**
1. Wrap tagging and question generation in the same `transaction.atomic()` block.
2. If they fail, the entire enrichment is rolled back and retried.
3. Alternatively, add a compensating transaction that deletes the note if downstream fails.

**Tests required:** Test that tagging/question failure causes enrichment retry.

---

### Finding 7: Stale Chunk Resurrection Without Re-embedding (G14)

**Problem:** When a previously-stale chunk's content hash reappears, `index_document` sets `stale=False` but does not check if the embedding is NULL. If the chunk was stale before embeddings were generated, it remains unembedded.

**Why it matters:** Resurrected chunks are invisible to dense retrieval.

**Files/components affected:** `apps/retrieval/services.py` `index_document`

**Recommended approach:**
1. After resurrecting a chunk, check if `embedding IS NULL`.
2. If so, add it to the `embeddable` list for re-embedding.

**Tests required:** Test that resurrected chunks without embeddings get embedded.

---

## 18. Prioritized Remediation Plan

### P0 — Must Fix Before Production

| ID | Problem | Why It Matters | Files/Components | Recommended Approach | Dependencies | Tests Required |
|----|---------|---------------|------------------|---------------------|--------------|----------------|
| G1 | No real OCR provider | Cannot extract text from images | `providers/ocr/`, `registry.py` | Implement production OCR; add health checks | Vendor choice | Integration test with real image |
| G2 | No real LLM provider | Cannot generate real enrichment | `providers/llm/`, `registry.py` | Implement production LLM; add timeout | Vendor choice, API keys | Integration test with real LLM |
| G3 | RLS not enforced | Cross-user data leak | `docker-compose.yml`, settings, migrations | Create restricted role; wire into Django | DBA approval | RLS behavioral probe test |
| G16 | No enrichment E2E test | Unknown if integration works | `tests/` | Add E2E test with mock providers | None | E2E test |
| G17 | No idempotency tests | Race conditions undetected | `tests/` | Add concurrent job tests | None | Threading test |
| G6 | No LLM timeout | Worker hangs indefinitely | `enrichment_nodes.py`, `providers/llm/chain.py` | Add timeout to LLM calls | Provider SDK | Timeout injection test |

### P1 — Must Fix for Reliable Operation

| ID | Problem | Why It Matters | Files/Components | Recommended Approach | Dependencies | Tests Required |
|----|---------|---------------|------------------|---------------------|--------------|----------------|
| G5 | Change magnitude placeholder | Coalescing broken | `ai_classroom/services.py` | Store/compare descriptor hashes | None | Coalescing test |
| G7 | Enrichment retry waste | Expensive retries | `ai_classroom/services.py`, `langgraph/` | Add checkpointing or LLM result cache | LangGraph support | Failure injection test |
| G8 | Partial enrichment failure | Inconsistent state | `ai_classroom/services.py` | Wrap tagging in transaction | None | Tagging failure test |
| G9 | Embedding failure no retry | Chunks stuck unembedded | `retrieval/services.py` | Add try/except; retry logic | None | Embedding failure test |
| G10 | Random reference chunks | Low-quality gap filling | `ai_classroom/enrichment_nodes.py` | Retrieve by gap relevance | None | Retrieval relevance test |
| G14 | Stale resurrection without re-embed | Missing embeddings | `retrieval/services.py` | Check and embed after resurrection | None | Resurrection test |
| G15 | No optimistic locking | Lost concurrent edits | `documents/services.py` | Add version field; select_for_update | Migration | Concurrency test |
| G22 | No backup automation | Data loss risk | `docker-compose.yml`, `config/celery.py` | Add Celery Beat service | None | Backup/restore drill |
| G20 | CORS not configured | CSRF risk | `config/settings/` | Add django-cors-headers | None | CORS test |

### P2 — Important Improvements

| ID | Problem | Why It Matters | Files/Components | Recommended Approach | Dependencies | Tests Required |
|----|---------|---------------|------------------|---------------------|--------------|----------------|
| G4 | Lexical embeddings only | Poor retrieval quality | `providers/embeddings/` | Switch to sentence-transformers | Model download | Retrieval quality test |
| G11 | Prompt injection defense | Potential prompt injection | `providers/llm/chain.py`, prompts | Wrap evidence in `<source>` tags | None | Prompt injection test |
| G12 | Inconsistent redaction | PII leakage | `providers/` | Shared redaction utility | None | Redaction test |
| G18 | No correlation IDs in workers | Hard to debug | `apps/jobs/tasks.py` | Propagate job_id to logs | None | Log correlation test |
| G19 | No aggregated metrics | No visibility | `apps/audit/` | Add Prometheus metrics | Prometheus setup | Metrics test |
| G23 | No golden dataset | No evaluation baseline | `apps/evaluation/` | Author 30-50 cases | Human labeling | Evaluation test |
| G24 | Uncalibrated verifier | Unreliable citations | `ai_classroom/services.py` | Calibrate thresholds | Golden dataset | Evaluation test |
| G25 | No storage GC | Cost leak | `providers/storage/` | Implement GC job | None | GC test |
| G26 | No profile deletion | Privacy risk | `apps/profiles/` | Implement anonymization | Legal review | Deletion test |

### P3 — Nice to Have

| ID | Problem | Why It Matters | Files/Components | Recommended Approach |
|----|---------|---------------|------------------|---------------------|
| G21 | CSRF_TRUSTED_ORIGINS missing | Security hardening | `.env`, settings | Add to environment config |
| G13 | Coalescing edge cases | Edge case robustness | `ai_classroom/services.py` | Add tests for boundary conditions |
| G21 | Hardcoded overlap logic | Chunk quality | `retrieval/services.py` | Implement word-based overlap |
| G22 | Backup RPO/RTO undefined | Disaster recovery | docs/runbooks | Document and test RTO/RPO |

---

## 19. Recommended Implementation Order

1. **P0-1:** Wire real LLM provider (even if Ollama local) — unlocks all AI features
2. **P0-2:** Wire real OCR provider (Tesseract) — enables real document processing
3. **P0-3:** Fix RLS enforcement — security prerequisite
4. **P0-4:** Add LLM timeout — reliability prerequisite
5. **P1-1:** Fix change magnitude and coalescing — cost control
6. **P1-2:** Add enrichment checkpointing — reliability
7. **P1-3:** Wrap tagging in transaction — data consistency
8. **P1-4:** Fix stale chunk resurrection — correctness
9. **P2-1:** Switch to semantic embeddings — quality
10. **P2-2:** Add E2E and idempotency tests — confidence
11. **P2-3:** Add observability (metrics, correlation IDs) — operability
12. **P2-4:** Add backup automation — disaster recovery
13. **P3:** Golden dataset, verifier calibration, GC, deletion flow — maturity

---

## 20. Open Questions / Ambiguities

1. **What is the actual deployment role setup?** The architecture says "restricted role never wired into prod config" but no one has confirmed the production DB role strategy.
2. **What is the expected LLM timeout?** No timeout is configured; what is the SLA for enrichment jobs?
3. **What happens to users' data when profile is deleted?** No deletion/anonymization flow exists. Legal/privacy requirement unclear.
4. **How are reference books ingested?** `ReferenceBook` model exists but no admin ingestion endpoint or management command is documented.
5. **What is the golden dataset composition?** Evaluation runner exists but no datasets. What are the 30-50 representative notes?
6. **How are verifier thresholds calibrated?** Current values (0.60, 0.30) are placeholders. What is the target precision/recall?
7. **What happens when a user edits OCR before enrichment?** Architecture says users can edit, but `create_user_revision` triggers `enqueue_index_job`, which triggers `enrichment_job`? No, `create_user_revision` only enqueues index job, not enrichment. User must manually trigger enrichment.
8. **Can enrichment run on documents with no reference books?** Yes, but gap detection/filling will have no reference chunks. Is this intended?
9. **What is the expected behavior when LLM returns malformed JSON?** `validate_stage_output` raises `ValidationError` → job fails. Should there be a schema repair step?
10. **Is the `order_by("?")` for reference chunks intentional?** It makes enrichment non-deterministic. Is this acceptable?

---

*Report generated from codebase analysis on 2026-09-08. All code references are to the StudyAI repository at `/Users/yash/CV_Project/StudyAI`.*
