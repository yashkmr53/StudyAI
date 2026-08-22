# AI Pipeline — stage-by-stage reality after Phase 6

| Stage | Component | Status | Notes |
|---|---|---|---|
| Ingest triggers | finalize-upload / canvas finalize / user edit | ✅ | revisions + jobs |
| Logical job machinery | durable jobs, idempotent keys, claim, retries, dead-letter | ✅ | §19–20 tested |
| OCR | chain provider | 🔧 mock | synthetic lines; §30 open |
| Chunking | page-aware word packing + overlap window | ✅ | `build_chunks` |
| Embedding | hashing 384-d L2 | 🟡 local simplified | model/version stored per chunk |
| Dense index / Keyword index | HNSW cosine / tsvector GIN | ✅ | PostgreSQL only for dense |
| Hybrid fusion (RRF) | RetrievalService.search | ✅ | k=60 depth=50 untuned |
| **Enrichment draft** | MockLLM + jsonschema validation | ✅ mechanics 🔧 text | blocks derived from cited evidence only |
| **Gap detection** | coverage token-diff mock | ✅ mechanics 🔧 text | bounded gaps list |
| **Gap filling** | reference-cited filler blocks | ✅ mechanics 🔧 text | cites exact reference chunk |
| **Citation stitcher** | §12 source_refs assembly | ✅ | mechanical mapping |
| **Evidence verification** | rules-v1 lexical support classifier | ✅ mechanism ⚠️ uncalibrated thresholds | per-citation status+score+version |
| Persistence | EnrichedNote/Block/CitationBlock atomic write | ✅ | supersede-and-retain semantics |
| Question generation / Chat / Planner | — | ❌ | Phase 7 |

## Generation records (§13) — what is actually stored

Per enrichment: provider (`mock`), model (`mock-gpt`), prompt_version string joining all stage qualified names (`enrichment_draft:v1;gap_detection:v1;gap_filling:v1`), schema_version, generation_job link, created_at. PromptVersion rows seeded with templates + configuration. Per OCR revision: ocr_provider + attempted chain in snapshot.

## Model/provider swap points

| Role | Registry location | Swap action |
|---|---|---|
| LLM | `_build_llm`/registry + `ENRICHMENT_MODEL` setting | implement protocol; keep schemas identical |
| Embeddings | `get_embedding_provider` + version bump | new version ⇒ re-index all chunks |
| OCR | `_build_ocr` chain names | implement protocol; pipeline unchanged |
