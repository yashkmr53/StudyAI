# AI Classroom (Module 2)

## Implementation status: ❌ Not implemented

Empty app skeletons exist (`backend/apps/ai_classroom/`, `retrieval`, `questions`, `tests`, `chat`, `revision`, `references`) and a placeholder frontend route. No models, services, prompts, or endpoints.

## Subsystem status

| Feature | Status | Notes |
|---|---|---|
| Ingestion into canonical documents | ❌ | Shared with NoteSpace; Phase 3 |
| Page-aware chunking + context window | ❌ | Phase 5 |
| Local embeddings | ❌ | Provider protocol only (`providers/base.py`) |
| Hybrid retrieval (pgvector + tsvector + RRF) | ❌ | pgvector not installed; see [../ai/RAG_AND_RETRIEVAL.md](../ai/RAG_AND_RETRIEVAL.md) |
| Enrichment pipeline A–F | ❌ | See [../ai/AI_PIPELINE.md](../ai/AI_PIPELINE.md) |
| Citation generation & evidence verification | ❌ | Verification = evidence validation, never raw cosine threshold |
| Tag hierarchy w/ stable keys + TagChangeLog | ❌ | Renames must not change identity |
| Question generation (revision-bound) | ❌ | Staleness sets `stale=true`; attempts retained forever |
| Adaptive test assembly | ❌ | Deterministic selection over mastery/uncertainty/recency/difficulty |
| MasteryScoringService | ❌ | One shared service; unattempted = `not_assessed`, not zero |
| Chatbot (scoped retrieval + citations) | ❌ | Never retrieves cross-profile content |
| Revision planner | ❌ | Deterministic; no LLM required for v1 |

## Grounding contract (to enforce when built)

Priority: user's own notes → approved reference books → general model knowledge only where explicitly allowed. General knowledge must never be presented as coming from the user's notes. Retrieved content is untrusted data wrapped in `<source>` blocks with explicit do-not-follow-instructions framing (spec §72).

## Data separation contract

Source layer (`Document*`, `NoteChunk`, `Embedding`) is strictly separate from generated layer (`EnrichedNote`, `EnrichedNoteBlock`, `CitationBlock`). Every generated artifact records its exact source revision, model, prompt name+version, and schema version.

## Cost boundary

When the AI budget is exhausted, AI Classroom degrades gracefully to a disabled state; NoteSpace and source data remain fully available.
