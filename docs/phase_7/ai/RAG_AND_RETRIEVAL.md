# RAG and Retrieval — unchanged after Phase 7

Implementation as documented in [`../phase_5/ai/RAG_AND_RETRIEVAL.md`](../ai/RAG_AND_RETRIEVAL.md).

Phase 7 consumers added:

- **Chatbot**: `ChatService.ask` runs scoped `RetrievalService.search` (top 4) and grounds answers in the returned evidence with verified citations.
- **Evaluation harness**: retrieval cases run through the same service (`run_retrieval_cases`).

Reranking remains absent (explicitly optional for v1).
