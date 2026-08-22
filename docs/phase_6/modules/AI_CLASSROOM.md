# AI Classroom (Module 2)

## Implementation status after Phase 6

| Feature | Status | Where |
|---|---|---|
| Source layer: chunks + embeddings + full-text | ✅ Phase 5 | `apps/retrieval/` |
| Hybrid retrieval (dense+keyword RRF) | ✅ Phase 5 | `RetrievalService.search` |
| Reference-book corpus w/ READY gating | ✅ Phase 5 | `apps/references/` |
| **EnrichedNote / Blocks / Citations** | ✅ new | `apps/ai_classroom/models.py` |
| **Enrichment pipeline A–F, schema-validated** | ✅ mechanics 🔧 LLM text | `apps/ai_classroom/services.py` + `prompts.py` |
| **Evidence verifier (rules-v1)** | ✅ mechanism ⚠️ uncalibrated thresholds | `EvidenceVerifier` |
| **Provenance independence** (method ⊥ verdict) | ✅ | separate dimensions in schema/API |
| **enrich / enrichment / refresh-ai endpoints** | ✅ | DocumentViewSet actions |
| **ai_stale propagation on content change** | ✅ | index tail → notes flagged |
| Prompt registry w/ versions (§13) | ⚠️ registry real; model mocked | `PromptVersion` + prompts.py |
| Question generation / adaptive tests / mastery | ❌ Phase 7 | — |
| Tags hierarchy + stable identity | ❌ Phase 7 | — |
| Chatbot (scoped evidence-grounded) | ❌ Phase 7 | will consume RetrievalService |
| Revision planner | ❌ Phase 7 | deterministic; no LLM needed |

Grounding contract now partially enforced *structurally*: the mock LLM can only restructure supplied evidence, so nothing uncited can appear. With a real model this becomes behavioral (verifier + eval harness police it).
