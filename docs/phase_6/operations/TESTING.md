# Testing — after Phase 6

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite; dense/RLS legs skip)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=3): 89 found — 86 passed, 3 skipped

# Backend — integration profile (real PostgreSQL: dense + RLS execute)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests --noinput
# → OK: 89 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    89 total  (+9 new in Phase 6)
  Passing:        89 (PostgreSQL)
  Failing:        0
  Skipped:        3 under SQLite only (2 RLS + 1 dense-channel test)
Frontend tests:   1 passing; production build green
Coverage:         not measured
```

## Phase 6 test inventory — `tests/api/test_ai_classroom.py`

| Suite | Proves |
|---|---|
| `EnrichmentFlowTests` (4) | enrich → 202 → job succeeds → nested enrichment with llm-method blocks and per-citation verdicts incl. verifier_version; key_concept block cites its source chunk and is `supported`; second enrich short-circuits to the active note; user edit ⇒ index rerun ⇒ `ai_stale=true` on the note; foreign users get 404 on both GET and POST |
| `RefreshAiTests` (1) | refresh-ai supersedes the active note, retains it, and creates a new generation |
| `VerifierTests` (1) | not_verified without refs; exact-evidence ⇒ supported ≥0.60; partial/unrelated classifications per rules-v1 thresholds |
| `PromptRegistryTests` (1) | seeding creates exactly three active v1 prompts and is idempotent |
| `EvalHarnessTests` (2) | citation precision/recall math = 1.0 on crafted supported+unsupported fixture with EvalRun persisted; retrieval recall_at_k = 1.0 against an indexed single-chunk corpus |

## Manual E2E performed

Against PostgreSQL through the running stack: enrich existing dijkstra document → 202 → succeeded → GET enrichment shows model/prompts/3 blocks — overview flagged **unsupported** (score 0.0), key_concept **supported** (1.0), gap_fill grounded in the READY reference book **supported** (0.83) → refresh-ai created a second generation while retaining the first (count=2).

## Honest gaps

- Verifier tested via pure classification + DB path; no adversarial citation cases yet.
- No concurrency tests for parallel enrich jobs on one document.
- RLS behavioral enforcement still untested as restricted role.
- Coverage unmeasured.
