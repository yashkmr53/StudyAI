# Traceability — Phase 6 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile tenant boundary + never-trusted client IDs (§3) | authorization service + scoped querysets everywhere incl. enrichment | foreign-access tests | ✅ |
| App-layer authorization on all queries (§3) | per-ViewSet filtering; enrichment latest-note scoped | isolation tests | ✅ |
| RLS on profile-scoped tables (§3) | migrations across subjects/canvas/documents/retrieval/ai_classroom (13 tables) | pg_policies manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context (§3/§47) | executor binds trusted context around handlers | GUC/no-leak tests | ✅ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions | ✅ |
| File validation (§23) / Rate limiting (§23) / Audit logging (§23) | validation ✅; rate limiting ❌; audit ❌ | validation tests | mixed — see rows |

## Authentication

Unchanged: JWT+Argon2 auth ✅ · atomic registration ✅ · revocation ✅ · password reset 🔧 · no sensitive logging ✅.

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 constraints incl. NoteChunk triple + active-note hash | migrations across apps | suites | ✅ |
| Canonical models + immutable revisions (§6/§48) | documents app | immutability tests | ✅ |
| NoteChunk source layer (§10) | retrieval app | chunk/index tests | ✅ |
| EnrichedNote/Block/CitationBlock generated layer (§9/§11/§12) | `apps/ai_classroom/models.py` | pipeline tests | ✅ |
| Provenance ⊥ verification independence (§12) | separate dimensions; verifier never rewrites method | method assertions under varying verdicts | ✅ |
| Source vs generated separation (§9) | chunks = source; enriched notes = generated; PDFs = rendered artifacts | structural | ✅ |
| Historical artifacts retained (§27) | stale chunks, superseded notes, old PDFs all retained | refresh/invalidation tests | ✅ |
| Tags with stable identity (§18) | — | — | ❌ |

## Canvas & offline / Ingestion / NoteSpace

Unchanged from Phase 4/5 audits: fencing ✅ · finalize transaction ✅ · outbox core ✅ (🟡 failure states) · upload flow 🟡 local storage · OCR 🔧 mock · NoteSpace PDFs ✅. See [`../phase_4/architecture/TRACEABILITY.md`](../../phase_4/architecture/TRACEABILITY.md).

## Retrieval foundation (Phase 5)

Unchanged: page-aware chunking w/ context window ✅ · incremental embed-only-new ✅ · pgvector dense HNSW ✅ · tsvector keyword GIN ✅ · RRF fusion ✅ · scoping/READY gating ✅ · local embeddings 🟡 hashing · reranking ❌ optional.

## AI Classroom intelligence (Phase 6 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Stage A Retrieve user + reference evidence (§11/§51) | scoped NoteChunk queries in `run_enrichment_job` | full-pipeline test | ✅ |
| Stage B Draft structured output (§11) | MockLLM `_draft` + jsonschema check | blocks/method assertions | ✅ mechanics 🔧 text |
| Schema validation on every node ≥ Draft (§11) | `validate_stage_output` per stage call | schema-failure path raises | ✅ |
| Stage C Gap detection (§11/§51) | token-diff mock vs references → bounded gaps | reference-grounded E2E | ✅ mechanics 🔧 text |
| Stage D Gap filling from approved corpus only (§11/§51) | filler blocks cite exact reference chunks; no uncited invention possible | gap-fill citation test | ✅ mechanics 🔧 text |
| Stage E Citation stitcher → §12 source_refs shape | refs include source_type/chunk_id/document_id/page_number/revision_id/retrieval_score | citation-shape assertions | ✅ |
| Stage F Evidence verification — supported/partially/unsupported/not_verified (§12/§41) | `EvidenceVerifier` rules-v1 lexical support; NOT_VERIFIED without refs | classification unit tests + discriminating pipeline verdicts | ✅ mechanism |
| Verifier versioning + calibration (§12/§26) | verifier_version stored per citation; thresholds settings-driven but uncalibrated | — | ⚠️ calibration pending |
| Grounding priority notes→references→(no silent general knowledge) (§51/§72) | mock restructures only supplied evidence; gap_fill labels reference origin | E2E shows reference-sourced block | ✅ within mock limits |
| POST enrich / GET enrichment / POST refresh-ai (§60) | DocumentViewSet actions | api tests | ✅ |
| ai_stale propagation to dependent AI artifacts (§21/§27) | index_document tail update | edit-staleness test | ✅ |
| Job dedup for identical content (§20/§21) | descriptor-hash keyed jobs + active-note short-circuit | second-enrich test | ✅ |
| Coalescing window + quota budgets/graceful degradation (§21/§74) | manual refresh exists; budgets absent | — | ❌ |
| LangGraph workflow orchestration (§31-40) | explicit sequential stage functions w/ schemas (F-003) | full-pipeline test | 🟡 alternative orchestration |

## Evaluation & platform remainder

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| EvalRun records (§26/§29) | `apps/evaluation/models.py` | harness tests | ✅ |
| Retrieval metrics runner Recall@k/MRR/P@k (§26) | `runner.run_retrieval_cases` | fixture-math test | ✅ mechanics |
| Citation metrics runner support precision/recall (§26) | `runner.run_citation_cases` vs verifier verdicts | precision/recall fixture test | ✅ mechanics |
| Golden dataset ~30–50 notes + labeled claims (§26) | — | — | ❌ |
| Provider fallback chains — LLM side (§28) | protocol exists; single mock | — | ❌ n/a until real LLM |
| Tags/mastery/questions/tests/chat/planner (§16–18) | — | — | ❌ |
| Private storage + signed URLs (§23) | end-to-end local variant | roundtrip tests | 🟡 |
| OpenAPI authoritative (§32) | regenerated per phase | — | ✅ |
| Request IDs + logs (§25) | middleware + stage INFO lines | manual | ✅ |
| Metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32) | — | — | ❌ |
| Simplest infra for v1 (§32 #25) | no langgraph/broker/model-service deps | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |

## Counters

```text
Tracked requirements: 93
✅ 58   ⚠️ 4   🟡 6   🔧 2   ❌ 23
```
