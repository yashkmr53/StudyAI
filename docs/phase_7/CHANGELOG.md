# Changelog

## [0.8.0] — 2026-08-22 — Phase 7: Learning Features

| Field | Detail |
|---|---|
| Change | Implemented Phase 7 of the v4.1 order (§31 items 43–49): tag hierarchy w/ stable identity + changelog, revision-aware question generation, deterministic adaptive test assembly, transactional attempt grading + EMA mastery scoring, evidence-grounded chatbot with verified citations, revision overview/goals/planner |
| Reason | Completes Module 2's learning layer on top of the retrieval + enrichment foundation |
| Files/modules affected | `backend/apps/ai_classroom/{models,tagging,services}.py` (+migrations), `backend/apps/questions/**` (new app content), `backend/apps/tests/**` (models/services/views/migrations+RLS), `backend/apps/chat/**`, `backend/apps/revision/**`, `backend/providers/llm/mock.py`, `backend/apps/retrieval/services.py` (stale→question hook), `backend/apps/documents/views.py` (tags action), `backend/apps/documents/urls.py`, `backend/tests/api/test_learning_features.py`, `docs/phase_7/**` |
| Database migration | ai_classroom 0003 (Tag/DocumentTag/TagChangeLog) · questions 0001 · tests 0001 · 0002_phase7_rls · chat 0001 · revision 0001 |
| API impact | Added `GET /documents/{id}/tags`; `POST/GET /tests`, `GET /tests/{id}`, `POST /tests/{id}/attempts`; `POST/GET /chat/sessions`, `POST/GET /chat/sessions/{id}/messages`; `GET /revision/overview`, `POST+GET /revision/goals`, `GET /revision/plans`; new error usage: 409 IDEMPOTENCY_CONFLICT on attempt replay |
| Breaking changes | none |

### Backend

- **Tags**: Tag hierarchy anchor (subject FK + parent FK) with unique(subject, stable_key); DocumentTag links carrying generation-job provenance; TagChangeLog append-only with ADDED/LINKED/RENAMED entries and deletion-surviving key snapshots; rule-based extraction in enrich tail skipping subject-less documents.
- **Questions**: deterministic MCQs from active chunks via MockLLM question_generation:v1 — seeded shuffle by chunk id; unique(revision, hash, question_key); stale propagation when source chunks supersede during indexing.
- **Tests/mastery**: TestGenerationService priority ordering (0.6 weakness + 0.25 recency + 0.15 difficulty, pk tie-break); attempts created + graded inside one transaction with MasteryScoringService EMA update; replay → 409 IDEMPOTENCY_CONFLICT; answer hidden until attempted.
- **Chat**: ChatService.ask persists user message, retrieves scoped evidence (top 4), generates extractive answer citing chunk ids, verifies citations via rules-v1, persists assistant message with model/chat:v1 provenance.
- **Planner**: overview endpoint reporting per-tag not_assessed/weak/fair/strong; goals CRUD-lite persisted; plans computed deterministically from weakness/urgency/failures/insufficient weights across a ≤14-day schedule.

### Verification

Backend suite: 101 tests — green on PostgreSQL (101/101) and SQLite (98 pass + 3 skips). Manual E2E: refresh-ai generated 4 tags + question; adaptive test assembled deterministically; correct attempt graded true with mastery 0.38/weak; chat answered with 3 verified citations; planner produced a 15-day schedule honoring hours_per_week. Frontend build + vitest green.

## [0.7.0] — Phase 6 · earlier
See [`../phase_6/CHANGELOG.md`](../phase_6/CHANGELOG.md).
