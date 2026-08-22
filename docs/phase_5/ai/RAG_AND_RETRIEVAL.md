# RAG and Retrieval — as actually built (Phase 5)

The retrieval system now **exists and runs**. This page documents the implemented reality; earlier design-only versions: [`../phase_4/ai/RAG_AND_RETRIEVAL.md`](../ai/RAG_AND_RETRIEVAL.md).

## Implemented pipeline

```text
Query
 ↓ scope filters: profile ownership OR platform-reference · optional subject · stale=false
Dense retrieval — pgvector cosine over HNSW index      top-50
 +
Keyword retrieval — SearchRank over tsvector GIN       top-50
 ↓ Reciprocal Rank Fusion (k = 60)
 ↓ top-k evidence with per-channel + fused scores
 ↓ READY-gate reference chunks defensively
Evidence → caller (search API today; chat/enrichment later)
```

## Parameters as configured

| Parameter | Value | Source |
|---|---|---|
| Chunk target size | 120 words | `CHUNK_WORDS` |
| Overlap/context window | 30 words carried into next chunk | `CHUNK_OVERLAP_WORDS` |
| Embedding model/version | hashing / `hashing-384-v1` | settings + registry |
| Dimensions | 384 | `EMBEDDING_DIMENSIONS` |
| Vector index | HNSW, `vector_cosine_ops` | migration `retrieval/0002` |
| FTS config | `'english'`, GIN index | same migration |
| RRF k / candidate depth | 60 / 50 | `RETRIEVAL_RRF_K`/`RETRIEVAL_CANDIDATES` |
| Reranking | not present — explicitly optional for v1 | §14 |

## What is genuinely working

- Incremental indexing: unchanged pages never re-chunked or re-embedded (hash-diff).
- Dense leg verified only on PostgreSQL; SQLite unit runs fall back to keyword-only.
- Scoping tested: cross-user leakage test passes; non-READY books excluded.
- Reference chunks carry `profile=NULL` and are visible to every authenticated user.

## Explicitly missing stages (say-so per requirements)

Reranking ❌ · query expansion ❌ · semantic (model-based) embeddings ❌ until model swap · citation metadata beyond chunk/document/page refs ❌ (arrives with enrichment Phase 6) · retrieval evaluation metrics ❌ (Recall@k etc. not measured — [AI_EVALUATION.md](AI_EVALUATION.md)).
