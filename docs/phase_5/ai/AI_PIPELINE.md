# AI Pipeline

## Status after Phase 5

The pipeline now extends one stage further downstream: **OCR → chunking → embedding → indexed retrieval**. OCR itself remains 🔧 mocked; embeddings are 🟡 hashing-based.

## Stage inventory

| Stage | Component | Status | Notes |
|---|---|---|---|
| Ingest triggers | finalize-upload / canvas finalize / user edit | ✅ | revisions + jobs |
| Logical job machinery | durable jobs, idempotency keys | ✅ | §19–20 semantics tested |
| Claim / RLS context / retries | executor | ✅ | trusted profile from job payload |
| Primary→fallback OCR | chain provider | 🔧 mock providers | §30 open decision |
| Text normalization | existence/readability checks | 🟡 | no enhancement |
| **Chunking** | `build_chunks` page-aware word packing w/ overlap window | ✅ new in Phase 5 | deterministic pure function |
| **Embedding** | HashingEmbeddingProvider 384-d L2 | 🟡 new in Phase 5 | model+version stored per chunk |
| **Dense index** | pgvector HNSW cosine | ✅ new in Phase 5 | PostgreSQL only |
| **Keyword index** | tsvector GIN + SearchRank | ✅ new in Phase 5 | english config |
| **Hybrid fusion** | RRF k=60 | ✅ new in Phase 5 | constants untuned |
| Retrieval service/API | RetrievalService + POST /search | ✅ new in Phase 5 | scoping enforced |
| Enrichment (LLM) | — | ❌ | Phase 6 |
| Tags/Questions/Chat/Revision | — | ❌ | Phase 7 |

## Provider/model inventory (live)

| Role | Provider | Model/Version | Input | Output | Recorded per artifact |
|---|---|---|---|---|---|
| OCR | mock (`mock`, `mock_low_confidence`, `failing`) | pipeline `mock-v1` | image key | lines+bbox+confidence | `DocumentPageRevision.ocr_provider` + snapshot attempted-chain |
| Embeddings | hashing (local) | `hashing-384-v1` | chunk/query text | 384-d L2 vector | `NoteChunk.embedding_model/_version` |

Swap points: `_build_ocr` and `get_embedding_provider` registries — business logic untouched at swap time.
