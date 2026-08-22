# Traceability — Phase 7 state

Answers: *"Where in the code is this architecture requirement actually implemented?"*

Legend: ✅ · ⚠️ partial · 🟡 simplified · 🔧 mocked/stubbed · ❌ not implemented

## Security & multi-tenancy

| Requirement (spec §) | Implementation | Tests | Status |
|---|---|---|---|
| Profile tenant boundary; untrusted client IDs (§3) | authorization service + scoped querysets across all new endpoints | isolation suites | ✅ |
| RLS on profile-scoped tables (§3) | migrations now cover 23 tables incl. tests/chat/revision/tags/questions/mastery | pg_policies manual check | ⚠️ superuser bypasses locally |
| Transaction-local RLS context (§3/§47) | executor binding | GUC tests | ✅ |
| Consistent error envelope (§61) | handlers | suites | ✅ |
| File validation (§23) ✅ · Rate limiting ❌ · Audit logging ❌ | — | — | mixed |

## Authentication
Unchanged: JWT+Argon2 auth ✅ · registration ✅ · revocation ✅ · password reset 🔧 · logging hygiene ✅.

## Data model & integrity

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| §66 constraints incl. Tag(subject,stable_key), Question triple, attempt/test uniqueness | migrations across apps | constraint/duplicate tests | ✅ |
| Canonical models + immutable revisions (§6/§48) | documents app | suites | ✅ |
| NoteChunk source layer + hybrid indexes (§10/§32/§33) | retrieval app | retrieval suite | ✅ |
| Generated layer EnrichedNote/Blocks/Citations (§9/§11/§12) | ai_classroom models | pipeline tests | ✅ |
| Provenance ⊥ verification independence (§12) | separate dimensions | method-vs-verdict assertions | ✅ |
| Historical retention incl. attempts on stale questions (§17/§27) | stale flags only; no deletes | staleness test | ✅ |
| Tags stable identity independent of display names (§18) | `TaggingService.rename_tag` + changelog | rename test | ✅ |

## Canvas & offline / Ingestion / NoteSpace / Retrieval

Unchanged from prior audits ([`../phase_5/architecture/TRACEABILITY.md`](../../phase_5/architecture/TRACEABILITY.md)): fencing/finalize ✅, outbox core ✅ (🟡 failure states), upload flow 🟡 local storage, OCR 🔧, hybrid retrieval ✅ (reranking ❌ optional), embeddings 🟡 hashing.

## Learning features (Phase 7 core)

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Rule-based tagging after enrichment w/ provenance job link (§53) | `TaggingService.extract_for_document` in enrich tail | rerun-stability test | ✅ extraction lexical 🟡 |
| TagChangeLog additions/renames/links (§18/§53) | changelog writes at each transition | rename/log test | ✅ |
| Documents without subject skip tagging | guard returns [] | implicit via subject-less docs | ✅ behavior, documented |
| MCQ generation bound to revision+chunk (§17/§54) | QuestionGenerationService + MockLLM question_generation:v1 | generation tests | ✅ mechanics 🔧 text |
| unique(revision, hash, question_key) (§66) | Question constraint | get_or_create dedupe | ✅ |
| Stale flag when source superseded; attempts retained (§17) | index tail update + no-delete policy | staleness test | ✅ |
| Deterministic adaptive selection (weakness/recency/difficulty) (§55) | TestGenerationService priority ordering | determinism test | ✅ constants untuned |
| Attempt grading single transaction (§56/§67-adjacent) | attempts action atomic block | grading test | ✅ |
| Replay protection per question (idempotency) | 409 IDEMPOTENCY_CONFLICT on duplicate | duplicate test | ✅ |
| MasteryScoringService EMA shared service (§18/§65) | `apps/tests/services.py::MasteryScoringService` | value/status assertions | ✅ constants untuned |
| not_assessed ≠ zero (§18) | absent rows + overview reporting | overview test | ✅ |
| GET /documents/{id}/tags (§60) | DocumentViewSet.tags action | tags endpoint used in flow | ✅ |
| POST/GET/GET{id} tests endpoints (§60) | TestViewSet | adaptive tests | ✅ |
| POST /tests/{id}/attempts (§60) | attempts action | grading/idempotency tests | ✅ |
| Chat sessions create/list/retrieve + messages GET/POST (§60) | ChatSessionViewSet | chat tests | ✅ |
| Chat scoped retrieval — never cross-profile (§16) | session profile drives search scoping | isolation test | ✅ |
| Grounded answer + citations persisted w/ model+prompt version (§16/§57) | ChatService.ask + ChatMessage fields | flow test asserts citations+verdict | ✅ answer text 🔧 mock |
| RevisionGoal creation + listing (§58/§60) | goals view | goal test | ✅ |
| Overview with not_assessed statuses (§58/§60) | overview view | shape/status test | ✅ |
| Deterministic plan builder prioritizing weakness→urgency→failures→insufficient (§58) | RevisionPlanningService.build_plan | plan-shape test | ✅ weights untuned |
| Plans computed without LLM (§58) | pure scoring/bucketing | deterministic output | ✅ |

## Intelligence remainder (Phase 6 state)

Unchanged rows: enrichment stages A–F ✅ mechanics 🔧 mock LLM text · schema validation every node ✅ · verifier rules-v1 ✅ thresholds ⚠️ · LangGraph orchestration 🟡 sequential functions · prompt registry ⚠️ real registry/mock models.

## Platform remainder

| Requirement (§) | Implementation | Tests | Status |
|---|---|---|---|
| Provider abstraction; SDKs isolated (§24) | protocols + registries | structural | ✅ interfaces |
| Private storage + short-lived signed URLs (§23) | local variant end-to-end | roundtrip tests | 🟡 |
| OpenAPI authoritative (§32) | regenerated per phase | — | ✅ |
| Request IDs + structured logs (§25) | middleware + INFO lines | manual | ✅ |
| Metrics/status page (§25) | — | — | ❌ |
| Backup/restore tested (§32) | — | — | ❌ |
| Simplest infra for v1 (§32 #25) | no graph/model/broker deps required | — | ✅ |
| Versioned REST APIs (§22) | `/api/v1/**` | all suites | ✅ |
| Golden dataset + labeled citation cases (§26) | — | — | ❌ |
| Coalescing window/quota budgets (§21/§74) | — | — | ❌ |
| Rate limiting / audit logging (§23) | — | — | ❌ |

## Counters

```text
Tracked requirements: 104
✅ 73   ⚠️ 4   🟡 6   🔧 2   ❌ 19
```
