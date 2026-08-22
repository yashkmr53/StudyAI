# RAG and Retrieval

## Status: ❌ Not implemented — every stage below is missing

No chunk tables, no embeddings, no pgvector, no full-text columns, no retrieval service exist in the codebase. The pgvector extension is not installed on the dev database.

## Implemented prerequisites only

- Idempotency key format: `embedding:{chunk_id}:{content_hash}:{embedding_model_version}` (`shared/idempotency/keys.py`).
- `EmbeddingProvider` protocol (`providers/base.py`).
- Profile/subject scoping patterns that retrieval filters must reuse (enforced today for subjects; will extend to chunks).

## Target pipeline (design; none of it executable today)

```text
Query
 ↓ metadata filters (profile · subject · source authorization · revision validity)
Dense retrieval (pgvector)        +
Keyword retrieval (PostgreSQL tsvector)
 ↓ Reciprocal Rank Fusion
 ↓ optional reranking             ← explicitly optional in v1; not planned by default
 ↓ top-k evidence
 ↓ LLM (downstream consumers)
```

## Design parameters to be fixed at implementation time

| Parameter | Value |
|---|---|
| Chunk size / overlap | **Undecided** — spec requires page-aware incremental chunking with a context window so page boundaries don't break concepts |
| Embedding model / dimensions | **Undecided** — local model mandated (§2), provider unselected |
| pgvector index type (ivfflat/hnsw) / distance metric | Undecided |
| tsvector configuration | Undecided (language, weighting) |
| RRF constant, top-k values | Undecided |
| Reranking | Not planned for v1 unless evaluation justifies it |

## Isolation requirements (binding when built)

Every retrieval operation must filter on profile scope, subject scope, source authorization, and revision/content status. The chatbot must never retrieve another user's private content. Worker-side retrieval binds the same transaction-local RLS context as request-side code.

## Revision-aware invalidation (design)

Page revision change → content_hash change → affected chunks marked stale → re-chunk affected region → embed only new/changed chunks → invalidate dependent AI artifacts. Historical artifacts are retained, never mutated.

## Reference-book retrieval

Only books in `READY` state participate; users cannot modify platform reference documents. Nothing implemented.
