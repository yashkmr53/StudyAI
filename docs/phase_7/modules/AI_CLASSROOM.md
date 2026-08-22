# AI Classroom (Module 2)

## Implementation status after Phase 7

| Feature | Status | Where |
|---|---|---|
| Source layer (chunks/embeddings/full-text) | ✅ | `apps/retrieval/` |
| Hybrid retrieval (RRF) | ✅ | `RetrievalService.search` |
| Reference corpus w/ READY gating | ✅ Phase 5 | `apps/references/` |
| EnrichedNote/Blocks/Citations + verifier | ✅ Phase 6 | `apps/ai_classroom/` |
| **Tag hierarchy + stable identity + changelog** | ✅ new | `Tag`, `TagChangeLog`, `TaggingService` |
| **Question generation (revision-bound, staleness-aware)** | ✅ mechanics 🔧 text | `apps/questions/services.py` |
| **Adaptive test assembly (deterministic)** | ✅ new | `TestGenerationService` |
| **Attempt grading → mastery EMA** | ✅ new | `MasteryScoringService` |
| **Chatbot grounded + verified citations** | ✅ mechanics 🔧 answer text | `ChatService` |
| **Revision overview/goals/plans (no LLM)** | ✅ new | `RevisionPlanningService` |
| Verifier calibration dataset | ❌ | §26 pending |
| Coalescing window / quota budgets | ❌ | Phase 8 |

Grounding contract: enrichment/chat answers are extractive over supplied evidence with per-citation verdicts; general-knowledge mode does not exist. With the real-model swap, grounding becomes behavioral and policed by the evaluation harness.
