# RAG and Retrieval — unchanged after Phase 6

The retrieval system is as built in Phase 5: pgvector dense (HNSW) + tsvector keyword fused with RRF, scoping enforced in SQL, READY-gated reference chunks, incremental indexing on edits.

Full implementation documentation: [`../phase_5/ai/RAG_AND_RETRIEVAL.md`](../ai/RAG_AND_RETRIEVAL.md).

Phase 6 consumers of retrieval:

- Enrichment stage A retrieves user + reference evidence via direct NoteChunk queries (bounded 8/6).
- Gap filling selects reference chunks by topic match.
- The evaluation harness runs RetrievalService.search against labeled chunk ids (`run_retrieval_cases`).

Reranking remains absent (explicitly optional for v1).
