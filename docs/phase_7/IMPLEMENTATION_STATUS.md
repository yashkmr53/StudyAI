# Implementation Status — Phase 7

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~60% of full v4.1 scope (Phases 1–7 of 8 complete)
Completed:          Security foundation; canvas/offline; ingestion; NoteSpace;
                    retrieval foundation; enrichment intelligence; learning
                    layer — stable tags + changelog, revision-aware question
                    generation, deterministic adaptive selection, transactional
                    attempts + EMA mastery, grounded chatbot w/ verified
                    citations, revision overview/goals/plans
Partial:            RLS enforcement (dev superuser bypass), reaper scheduling,
                    prompt/model versioning (models mocked), local-FS storage
Mocked/stubbed:     OCR + LLM text generation (mock providers), password reset
Unimplemented:      Verifier/embedding calibration datasets, coalescing/quota
                    budgets, reranking stage, rate limiting, audit logging,
                    metrics/health endpoints, backups, CI, deployment artifacts,
                    NoteSpace/AI frontend polish beyond core screens
Major risks:        Synthetic content upstream (mock OCR/LLM); mastery EMA
                    constants untuned; no eval dataset; no backups/CI
```

## Phase 7 feature audit

### Tags & change log

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Tag model w/ hierarchy anchor | §18 | ✅ | `apps/ai_classroom/models.py::Tag` — subject FK + parent FK + stable_key + display_name; unique(subject, stable_key) per §66 | `TaggingTests` | Parent supports future Subject→Unit→Topic→Subtopic depth | Full 4-level taxonomy not exercised |
| Stable identity across renames | §18 | ✅ | `TaggingService.rename_tag` keeps row/stable_key, logs RENAMED | `test_rename_preserves_identity_and_logs` | — | No rename API endpoint yet (service-level) |
| TagChangeLog | §18/§53 | ✅ | ADDED/LINKED/RENAMED entries w/ job provenance; SET_NULL tag FK + key snapshot survives deletion | rename/log assertions | — | REMOVED path unused (no removal flow) |
| Rule-based extraction after enrichment | §53 | ✅ | `TaggingService.extract_for_document` — frequent significant tokens → find-or-create stable tags → DocumentTag links (+LINKED logs); runs in enrich tail | rerun-stability test | Documents without subject skip tagging (§18 anchors to subject) | Extraction is lexical, not semantic (mock-stage) |

### Question generation

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| MCQ generation grounded in chunks | §17/§54 | ✅ mechanics 🔧 text | `QuestionGenerationService.generate_for_document` via MockLLM question_generation:v1; distractors from sibling chunks | `QuestionGenerationTests` | Deterministic shuffle seeded by chunk id | Content synthetic until real LLM |
| Revision binding + uniqueness | §17/§66 | ✅ | source_revision_id/source_chunk_id recorded; unique(revision, hash, key) | generation tests | — | — |
| Stale propagation, attempts retained | §17/§27 | ✅ | index pass flags questions whose chunk was superseded; rows never deleted | `test_source_staleness_flags_questions` | — | — |
| Auto-generation hook | enrich tail | ✅ | run_enrichment_job tail calls generator | pipeline tests | Also re-runs via refresh-ai | No standalone generate endpoint (by design) |

### Adaptive tests & mastery

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| TestInstance/TestAttempt models | §17 | ✅ | `apps/tests/models.py` + TestQuestion through-table | adaptive suite | One attempt per (test, question) — replay ⇒ 409 IDEMPOTENCY_CONFLICT | — |
| Deterministic adaptive selection | §55 | ✅ | priority = 0.6·weakness + 0.25·recency + 0.15·difficulty-match; stable tie-break | `test_create_test_deterministic_selection` | Same state ⇒ identical selection (asserted) | Weights defaults, not tuned |
| Attempt grading + mastery update atomic | §56 | ✅ | `POST /tests/{id}/attempts` single transaction: attempt + MasteryScoringService.record_attempt | grading test | Returns updated mastery payload | — |
| MasteryScoringService shared | §18/§65 | ✅ | EMA: correct ⇒ m += (1−m)·0.4·(0.5+conf/2); wrong ⇒ m −= m·0.4·(0.5+(1−conf)/2) | value/status assertions | Shared by planner | Constants not tuned against data |
| not_assessed ≠ zero | §18 | ✅ | no row ⇒ status not_assessed; neutral 0.5 only inside selection scoring | overview test | — | — |

### Chatbot

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Scoped hybrid retrieval | §16/§57 | ✅ | RetrievalService with session profile + optional subject; cross-profile impossible by construction | chat isolation test | — | — |
| Grounded answer + citations persisted | §16/§57 | ✅ | assistant message stores citations[] (chunk/page/snippet/scores) + model + chat:v1 | chat flow test | Extractive answer from top evidence (mock) | Answer synthesis quality awaits real LLM |
| Citation verification on answers | §12/§16 | ✅ | EvidenceVerifier rules-v1 verdict stored on the citation block | flow test asserts verdict present | — | — |
| Sessions/messages endpoints | §60 | ✅ | create/list/retrieve sessions; GET+POST messages | api tests | — | — |
| Isolation between users | §16 | ✅ | queryset scoping; foreign session access → 404 | isolation test | — | — |

### Revision planning

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| RevisionGoal model | §58 | ✅ | `apps/revision/models.py` | goal creation test | subject optional, hours_per_week captured | — |
| Overview incl. not_assessed reporting | §18/§58 | ✅ | GET /revision/overview | overview test | Per-tag rows sorted weakest/not-assessed first | — |
| Deterministic plan builder | §58 | ✅ | priority = weakness·0.45 + urgency·0.25 + failures·0.20 + insufficient·0.10; round-robin day buckets (≤14 days, 2 sessions/day) | plan-shape test | No LLM required ✓ | Session count fixed; no calendar integration |

## Carried over

Phases 1–6 audits remain valid ([`../phase_6/IMPLEMENTATION_STATUS.md`](../phase_6/IMPLEMENTATION_STATUS.md)). OCR 🔧 and LLM 🔧 mocks unchanged; embeddings 🟡 hashing-grade.

## Final implementation audit

```text
Total architecture requirements tracked: 104   (was 93 after Phase 6)
Fully implemented:            73
Partially implemented:         4
Simplified/alternative:        6
Mocked/stubbed:                2
Not implemented:              19

Tests passing:   backend 101/101 (PostgreSQL); 98 pass + 3 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   3 under SQLite settings only (2 RLS + 1 dense-channel test)
Coverage:        not measured
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          tokens in localStorage; password reset stub
Known operational issues: no backups, no health endpoints, no CI, reaper
                          unscheduled, local-FS storage only
Known AI-quality issues:  all generated content synthetic (mock OCR+LLM);
                          verifier/mastery/planner constants uncalibrated;
                          eval datasets empty
Known architectural deviations: sequential orchestration (F-003);
                          revision_ids lists (D-002/E-002); signed-URL JSON
                          payloads (D-004); /search beyond blueprint (F-004/E-009)
```
