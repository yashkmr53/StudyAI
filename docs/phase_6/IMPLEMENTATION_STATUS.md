# Implementation Status — Phase 6

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~52% of full v4.1 scope (Phases 1–6 of 8 complete)
Completed:          Security foundation; canvas/offline; ingestion; NoteSpace;
                    retrieval foundation (Phase 5); AI Classroom intelligence:
                    generated-layer models, prompt registry, schema-validated
                    enrichment pipeline A–F, rules-based evidence verifier,
                    enrich/enrichment/refresh-ai endpoints, ai_stale
                    propagation, evaluation harness mechanics
Partial:            RLS enforcement (dev superuser bypass), reaper scheduling,
                    prompt/model versioning (registry real, models mocked),
                    local-FS storage serving
Mocked/stubbed:     LLM text generation (mock provider), OCR providers,
                    password-reset email
Unimplemented:      Question generation + adaptive tests, mastery service,
                    chatbot, revision planner, tags hierarchy, verifier
                    calibration dataset, coalescing/quota budgets,
                    rate limiting, audit logging, metrics/health endpoints,
                    backups, CI, deployment artifacts
Major risks:        Enrichment content is synthetic (mock LLM); verifier
                    thresholds uncalibrated; no eval dataset yet
```

## Phase 6 feature audit

### Generated-layer models

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| EnrichedNote | §9 | ✅ | `apps/ai_classroom/models.py` | `tests/api/test_ai_classroom.py::EnrichmentFlowTests` | document FK, revision_ids list, generation_job FK, provider/model/prompt_version/schema_version | — |
| EnrichedNoteBlock | §9 | ✅ | same file | block assertions | block_index/type/title/content/generation_method/source_chunk_ids | — |
| CitationBlock | §12 | ✅ | same file | citation assertions | source_refs[] per §12 shape incl. page_number/retrieval_score; OneToOne per block | Multiple citations per block collapse into one refs array |
| Provenance ⊥ verification independence | §12 invariant | ✅ | separate dimensions: `generation_method` on blocks vs `verification_status` on citations; verifier never rewrites method | pipeline asserts method stays `llm` even when verdicts vary | — | — |
| RLS on all three tables | §3 | ⚠️ | migration `ai_classroom/0002_enable_rls.py` EXISTS chains | pg_policies manual check | Same superuser caveat as all phases | Restricted-role behavioral test pending |

### Enrichment pipeline

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Stage A Retrieve | §11/§51 | ✅ | document chunks + READY reference chunks via NoteChunk queries | full-pipeline test | Capped 8 user / 6 reference evidence items | No rrf-ordered selection yet (recency/index order) |
| Stage B Draft — structured output | §11 | ✅ mechanics 🔧 text | MockLLMProvider `_draft`; jsonschema validation after call | blocks/method assertions | Overview + key_concept blocks derived from cited chunks only | Text is synthetic restructuring |
| Schema validation every node ≥ Draft | §11 | ✅ | `prompts.py::validate_stage_output` with jsonschema schemas per stage | schema-failure path raises ValidationError | Schemas registered in SCHEMAS map | — |
| Grounding priority: notes → references → nothing uncited | §51/§72 | ✅ | draft cites user chunks; gap_fill cites reference chunks; mock cannot invent uncited content (only restructures supplied evidence) | gap-fill reference-citation test | General-knowledge path deliberately unused | — |
| Stage C Gap detection | §11/§51 | ✅ mechanics 🔧 text | token-diff between user and reference coverage → bounded gaps list | exercised in reference-grounded E2E | Deterministic lexical diff, not semantic understanding | — |
| Stage D Gap filling from approved corpus | §11/§51 | ✅ mechanics 🔧 text | filler blocks cite the exact reference chunk supplying content | E2E smoke shows gap_fill supported 0.83 against reference book | — | — |
| Stage E Citation stitcher | §11/§12 | ✅ | mechanical mapping of block sources to §12 source_refs shape {source_type, chunk_id, document_id, page_number, revision_id, retrieval_score} | citation-shape assertions | retrieval_score null until ranking integration | — |
| Stage F Evidence verifier | §12/§41 | ✅ mechanism ⚠️ thresholds | `EvidenceVerifier` (rules-v1): lexical support ratio vs cited chunk contents; supported ≥0.60 / partially ≥0.30 / else unsupported; NOT_VERIFIED without refs | classification unit tests + pipeline verdicts | Verdict demonstrably discriminates: meta-text overview flagged unsupported while verbatim-derived key concepts score supported 1.0 | Thresholds uncalibrated (needs labeled set); similarity is candidate signal, not proof — matches spec caveat |
| Failure isolation | §28/§52 | ✅ | failures mark job retryable/dead-letter only; documents/PDFs untouched | structural (executor paths) | — | — |

### API & scheduling

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| POST /documents/{id}/enrich | §60 | ✅ | `DocumentViewSet.enrich` — 200 existing note / 202 job | flow tests | Idempotency: active note w/ same descriptor short-circuits | — |
| GET /documents/{id}/enrichment | §60 | ✅ | nested serializer (blocks+citations) incl. ai_stale flag | detail tests | Foreign → 404 | — |
| POST /documents/{id}/refresh-ai | §60 | ✅ | forced regeneration; old note superseded=true retained | refresh test | — | — |
| ai_stale propagation on content change | §21/§27 | ✅ | index_document tail flips ai_stale on dependent enriched notes | edit-staleness test | Questions/tags will reuse this hook | — |
| Job deduplication for identical content | §21/§20 | ✅ | descriptor-hash keyed jobs | second-enrich test | — | — |
| Coalescing window + quota budgets | §21/§74 | ❌ | — | — | Manual refresh is the pressure valve today | Hardening phase |

### Evaluation harness

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| EvalRun records | §26/§29 | ✅ | `apps/evaluation/models.py` + runner `record_run` | harness math tests | Metrics JSON stored per run | — |
| Retrieval metrics runner | Recall@k/MRR/Precision@k | ✅ mechanics | `runner.run_retrieval_cases` over labeled chunk ids | fixture-math test | Dense leg on PG only | Dataset itself empty (❌) |
| Citation metrics runner | support precision/recall | ✅ mechanics | `runner.run_citation_cases` against rules-v1 verifier verdicts | precision/recall=1.0 on crafted fixture | — | Dataset itself empty (❌) |
| Command interface | ops ergonomics | ✅ | `manage.py run_ai_evaluation --file … [--user --k]` | used by tests | — | — |
| Golden dataset / labeling process | §26 | ❌ | — | — | ~30–50 notes + labeled claims needed | Phase 7/8 work |

## Carried over

Phases 1–5 audits remain valid ([`../phase_5/IMPLEMENTATION_STATUS.md`](../phase_5/IMPLEMENTATION_STATUS.md)). OCR providers 🔧; embeddings 🟡 hashing-grade.

## Final implementation audit

```text
Total architecture requirements tracked: 93   (was 87 after Phase 5)
Fully implemented:            58
Partially implemented:         4
Simplified/alternative:        6
Mocked/stubbed:                2
Not implemented:              23

Tests passing:   backend 89/89 (PostgreSQL); 86 pass + 3 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   3 under SQLite settings only (2 RLS + 1 dense-channel)
Coverage:        not measured
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          tokens in localStorage; password reset stub
Known operational issues: no backups, no health endpoints, no CI, reaper
                          unscheduled, local-FS storage only
Known AI-quality issues:  enrichment text synthetic (mock LLM); verifier
                          thresholds uncalibrated; eval datasets empty;
                          embedding quality lexical-grade
Known architectural deviations: sequential pipeline instead of LangGraph (F-003);
                          download endpoint returns signed-URL payload (D-004);
                          revision_ids lists generalize singular ids (D-002/E-002)
```
