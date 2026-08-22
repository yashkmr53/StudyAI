# AI Classroom (Module 2)

## Implementation status: 🟡 Foundation implemented (Phase 5); intelligence features ❌ pending (Phases 6–7)

| Feature | Status | Notes |
|---|---|---|
| Source layer: NoteChunk + embeddings + tsvector | ✅ | `apps/retrieval/models.py` |
| Revision-aware incremental chunking | ✅ | hash-diff indexing; stale-out retained |
| Local embeddings | 🟡 | hashing embedder (lexical-grade) — model swap point documented |
| pgvector dense retrieval | ✅ | HNSW cosine index; PostgreSQL only |
| Keyword full-text retrieval | ✅ | tsvector GIN + SearchRank |
| Hybrid fusion (RRF) | ✅ | k=60, depth 50, configurable |
| Reference-book corpus + READY gating | ✅ | management-command ingestion; read-only to users |
| Search API | ✅ | `POST /api/v1/search` (extension F-004) |
| Enrichment pipeline / citations / verification | ❌ | Phase 6 — see [../ai/AI_PIPELINE.md](../ai/AI_PIPELINE.md) |
| Tags / mastery / questions / adaptive tests | ❌ | Phase 7 |
| Chatbot (evidence-grounded) | ❌ | Phase 7 — will consume RetrievalService |
| Revision planner | ❌ | Phase 7 |

## Grounding contract reminder

When enrichment/chat land: user notes first, reference books second, general knowledge only where explicitly allowed; retrieved content wrapped as untrusted `<source>` data (§72); every generated artifact records its exact source revisions.
