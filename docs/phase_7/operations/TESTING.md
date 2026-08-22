# Testing — after Phase 7

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite; dense/RLS legs skip)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=3): 101 found — 98 passed, 3 skipped

# Backend — integration profile (real PostgreSQL: dense + RLS execute)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests --noinput
# → OK: 101 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    101 total  (+12 new in Phase 7)
  Passing:        101 (PostgreSQL)
  Failing:        0
  Skipped:        3 under SQLite only (2 RLS + 1 dense-channel test)
Frontend tests:   1 passing; production build green
Coverage:         not measured
```

## Phase 7 test inventory — `tests/api/test_learning_features.py`

| Suite | Proves |
|---|---|
| `TaggingTests` (3) | tags created with lowercase stable keys + display names; re-running extraction keeps the same Tag rows (stable identity); rename preserves stable_key, updates display_name and writes a RENAMED changelog entry |
| `QuestionGenerationTests` (2) | MCQs generated grounded in chunks with model/prompt recorded, valid option/answer shape; source-chunk staleness flags the question without deleting it |
| `AdaptiveTestTests` (2) | POST /tests returns ≤N questions with unanswered state and identical selection for identical state (determinism §55); correct attempt grades true, updates mastery payload (value/status/tag), replay returns 409 |
| `MasteryNotAssessedTests` (1) | overview reports not_assessed statuses for linked-but-unattempted tags (§18) |
| `ChatTests` (2) | chat grounds answer in evidence ("Dijkstra…" appears) with citations incl. verifier verdict; foreign user gets 404 on another user's session messages |

## Manual E2E performed

Against PostgreSQL through the running stack with a subject assigned to an existing document:

- refresh-ai → tail produced 4 DocumentTag links + 1 question.
- POST /tests → deterministic 2-question instance; correct attempt → mastery 0.38/weak on tag `939cd7`.
- Chat session question "What does Dijkstra compute?" → grounded answer citing 3 chunks, verdict supported.
- Revision overview listed not_assessed tags; plans endpoint returned 15-day schedule honoring hours_per_week.

## Honest gaps

- No concurrency tests for parallel attempts on the same question (DB unique constraint guards duplicates).
- Planner determinism asserted structurally (shape), not value-for-value across runs.
- RLS behavioral enforcement still untested as restricted role; coverage unmeasured.
