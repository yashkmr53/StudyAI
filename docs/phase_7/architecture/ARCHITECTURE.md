# Architecture — after Phase 7

Delta documentation: Phases 1–6 architecture remains valid ([`../phase_6/architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md)).

## Module status board

| Module / Layer | Status |
|---|---|
| Security foundation | ✅ |
| Canvas + offline sync | ✅ |
| Shared ingestion | ✅ (OCR 🔧 mock) |
| NoteSpace (Module 1) | ✅ |
| AI Classroom foundation + intelligence | ✅ mechanics 🔧 LLM text |
| **Learning features** | ✅ new — tags/questions/tests/mastery/chat/planner |
| Ops hardening | ❌ Phase 8 |

## New backend components (Phase 7)

```text
apps/ai_classroom/   + Tag · DocumentTag · TagChangeLog · tagging.py
apps/questions/      + Question · QuestionTagLink · QuestionGenerationService
apps/tests/          + TestInstance/TestQuestion/TestAttempt · MasteryScore
                       MasteryScoringService · TestGenerationService
                       views (create/list/retrieve/attempts) · RLS migration
apps/chat/           + ChatSession/ChatMessage · ChatService · viewset+messages
apps/revision/       + RevisionGoal · RevisionPlanningService · three endpoints
```

## Learning loop (implemented end-to-end)

```text
Enrich tail → tags (stable keys, changelog) → MCQs (revision-bound)
POST /tests → deterministic adaptive selection → instance
POST attempts → grade + EMA mastery (single transaction)
Chat messages → scoped retrieval → grounded answer → verified citations
Revision overview/goals/plans → mastery-driven deterministic schedule
```

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| Tag identity independent of display names (§32 #18) | rename keeps row/stable_key; changelog records |
| Historical attempts retained when questions stale (§32 #17) | flags only; no deletes; tests assert retention |
| not_assessed ≠ zero anywhere (§18) | absent rows reported as not_assessed |
| Chat never retrieves cross-profile content (§16) | session-scoped search + owner-filtered sessions |

## Component inventory status

| Area | Status |
|---|---|
| Foundation / canvas / ingestion / NoteSpace / retrieval / intelligence | ✅ (mocks as noted) |
| Learning layer | ✅ (constants untuned) |
| Ops hardening | ❌ final phase |
