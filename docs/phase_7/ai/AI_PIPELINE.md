# AI Pipeline — stage-by-stage reality after Phase 7

| Stage | Component | Status | Notes |
|---|---|---|---|
| Ingest triggers / job machinery / claim+RLS+retries | Phases 3–5 | ✅ | unchanged |
| OCR | chain provider | 🔧 mock | §30 open |
| Chunking / Embedding / Dense+Keyword indexes / RRF | retrieval app | ✅ (embeddings 🟡 hashing) | Phase 5–6 |
| Enrichment draft/gap/fill + citations + verification | ai_classroom services | ✅ mechanics 🔧 LLM text | Phase 6 |
| **Question generation** | MockLLM question_generation:v1 → deterministic MCQs bound to revision+chunk | ✅ mechanics 🔧 text | new in Phase 7 |
| **Chat answering** | MockLLM chat:v1 extractive answer over top evidence, citations verified by rules-v1 | ✅ mechanics 🔧 text | new in Phase 7 |

## Generation records stored (§13 compliance)

| Artifact | Fields recorded |
|---|---|
| EnrichedNote | provider, model, prompt_version (all stages), schema_version, generation_job link |
| Question | generation_model (`mock-gpt`), prompt_version (`question_generation:v1`), source_revision_id, source_chunk_id |
| ChatMessage | model, prompt_version (`chat:v1`), citations incl. per-citation verifier verdicts |

## Swap points unchanged

LLM/embedding/OCR registries in `providers/registry.py` + `_build_llm`; question/chat behavior keys off prompt names so a real provider slots in without pipeline changes.
