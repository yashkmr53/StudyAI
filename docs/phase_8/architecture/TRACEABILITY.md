# Traceability — Final (Phase 8)

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile tenant boundary; untrusted client IDs (§3) | authorization service + scoped querysets across all endpoints | isolation suites | ✅ |
| RLS on profile-scoped tables — 23 tables total (§3) | migrations: subjects/canvas/documents/retrieval/ai_classroom/tests/chat/revision bundles | pg_policies manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context incl. workers (§3/§47) | `shared/database/rls.py` executor binding | GUC/no-leak tests | ✅ |
| Consistent error envelope (§61) | `shared/exceptions/handlers.py` | envelope assertions | ✅ |
| File validation incl. magic bytes (§23) | storage view signature check → 422/413 envelopes | sniff/mismatch tests | ✅ |
| **Rate limiting** (§23) | scoped throttles auth 30/min · ai 120/min · live-settings class | 429 envelope test | ✅ single-node store only |
| **Audit logging** (§23) | AuditLog + service + staff listing GET /audit?action=… | register/login/logout/list tests | ✅ core events |
| Security headers (§23) | SecurityHeadersMiddleware | header test | ✅ |

## Authentication

JWT+Argon2+rotation/blacklist ✅ (`accounts/views.py`) · atomic registration ✅ · logout blacklisting ✅ · password reset 🔧 stub · login/logout/register audited ✅ · no sensitive logging ✅.

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 constraints (all) — profiles/subjects/canvas/documents/questions/tags/attempts/jobs/chats | app migrations | constraint/duplicate suites | ✅ |
| Canonical models + immutable revisions (§6/§48) | documents app | immutability tests | ✅ |
| NoteChunk source layer w/ vector+tsvector (§10) | retrieval models | index tests | ✅ |
| Generated layer EnrichedNote/Block/CitationBlock (§9/§11/§12) | ai_classroom models | pipeline tests | ✅ |
| Provenance ⊥ verification (§12) | separate dimensions | verdict-vs-method assertions | ✅ |
| Historical retention: stale chunks/questions, superseded notes, old PDFs (§27) | flags only, never delete | retention tests | ✅ |
| Tags stable identity + changelog (§18) | Tag/TagChangeLog/rename service | rename/stability tests | ✅ |
| Mastery not_assessed ≠ zero (§18) | absent-row semantics + overview reporting | overview test | ✅ |

## Canvas & offline / Ingestion / NoteSpace

Unchanged from Phase 4 audit ([`../phase_4/architecture/TRACEABILITY.md`](../../phase_4/architecture/TRACEABILITY.md)): fencing/finalize transaction ✅ · outbox core ✅ (failure states 🟡) · upload flow 🟡 local-FS · NoteSpace PDFs ✅.

## Retrieval & intelligence

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Page-aware chunking + context window (§10) | `build_chunks` | span/context test | ✅ |
| Incremental embed-only-new indexing (§10) | hash-diff in index_document | rerun test | ✅ |
| Edit invalidation → stale chunks/questions + ai_stale notes (§10/§27) | index tail hooks | invalidation tests | ✅ |
| pgvector dense HNSW (§32) | migration + CosineDistance queries | dense-channel test (PG) | ✅ |
| tsvector keyword GIN (§33) | SearchVectorField + SearchRank | keyword test | ✅ |
| RRF fusion + scoping + top-k (§14) | RetrievalService.search | retrieval suite | ✅ |
| Reranking stage (§14 optional) | — | — | ❌ explicitly optional |
| Enrichment A–F schema-validated nodes (§11) | run_enrichment_job + validate_stage_output | pipeline tests | ✅ mechanics 🔧 LLM text |
| Grounding priority notes→references→no silent general knowledge (§51/§72) | mock restructures supplied evidence only | reference-grounded E2E | ✅ within mock limits |
| Evidence verifier supported/partially/unsupported/not_verified (§12/§41) | EvidenceVerifier rules-v1 | classification unit tests + discriminating E2E verdicts | ✅ mechanism ⚠️ thresholds uncalibrated |
| Citation stitcher §12 source_refs shape | refs assembly in pipeline | shape assertions | ✅ |
| Prompt/model versioning records (§13) | PromptVersion registry seeded; per-artifact model/prompt fields | registry test | ⚠️ registry real, models 🔧 mocked |
| Reference books READY-gated ingestion (§15) | references app + ingest command | ready/exclusion tests | ✅ |
| Chatbot scoped grounded verified answers (§16) | ChatService.ask | flow/isolation tests | ✅ mechanics 🔧 answer text |
| Question generation revision-bound (§17/§54) | questions services | generation/staleness tests | ✅ mechanics 🔧 text |
| Deterministic adaptive selection (§55) | TestGenerationService priority ordering | determinism test | ✅ constants untuned |
| Attempt grading atomic + mastery update (§56) | attempts action + MasteryScoringService | grading/mastery tests | ✅ constants untuned |
| Revision overview/goals/plans deterministic no-LLM (§58) | revision views/services | planner tests | ✅ |
| Provider fallback chains — OCR (§28) | OCRChainProvider | fallback/dead-letter tests | ✅ mechanism / 🔧 providers |
| Provider fallback chain — LLM (§28/§50) | LLMChainProvider + registry chain | fallback unit test | ✅ mechanism / 🔧 providers |
| Daily AI budget graceful degradation (§21/§74) | budget.assert_within_budget → 429 RATE_LIMITED on enrich/chat | budget exhaustion test | 🟡 call-count proxy for cost |
| Coalescing window scheduling (§21) | — | — | ❌ manual refresh is the pressure valve |
| Evaluation harness runners (§26/§42) | citation + retrieval runners, EvalRun rows | fixture-math tests | ✅ mechanics; datasets ❌ |
| Regression gate monitoring (§55) | --assert-gte exit-code gate | gate behavior covered via runner fixture | ✅ command flag |

## Platform

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Provider abstraction; SDKs isolated (§24) | protocols + registries | structural | ✅ interfaces / 🔧 impls |
| Private storage + short-lived signed URLs (§23) | local variant end-to-end | roundtrip/forged tests | 🟡 local variant |
| OpenAPI authoritative (§32) | regenerated every phase | — | ✅ |
| Request IDs + structured logs (§25) | middleware + formatter | manual | ✅ |
| **Health endpoints** /readyz DB probe (§25) | shared.observability.views | readyz test | ✅ |
| **Internal status page metrics** (§25): job health/queue depth/dead-letter/provider usage/citation distribution/request p95s | /api/v1/status staff view | payload-shape test | ✅ v1 scope (in-memory histogram) |
| External APM/alerting (§25) | — | — | ❌ |
| Backup/restore commands + performed drill (§70/§31-54) | backup_database + verify_backup commands; drill executed (159 KB dump → restore → row counts matched) | drill output captured | ⚠️ done manually; scheduled automation ❌ |
| CI pipeline running full suites (hygiene) | .github/workflows/ci.yml (PG container + backend suite; node build/test) | workflow authored | ⚠️ authored, not yet executed on GitHub |
| Deployment artifacts compose/docker/nginx (§24) | backend/frontend Dockerfiles + docker-compose + deploy/nginx.conf | syntax review | 🟡 authored; clean-host drill pending |
| Load testing harness + §75 baseline (§53/§75) | scripts/load_test.py stdlib threads; all scenarios p95 < 500 ms | baseline captured | 🟡 small-scale local run |
| Simplest infra for v1 (§32 #25) | broker-free operation; no external AI APIs | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |
| Async endpoints 202 + job resource (§22) | revisions/pdf/enrich/retry | asserted | ✅ |

## Counters

```text
Tracked requirements: 111
✅ 81   ⚠️ 7   🟡 9   🔧 2   ❌ 13
```
