# Testing — after Phase 5

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite; dense channel + RLS legs skip)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=3): 80 found — 77 passed, 3 skipped

# Backend — integration profile (real PostgreSQL: dense channel + RLS execute)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests --noinput
# → OK: 80 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    80 total  (+13 new in Phase 5)
  Passing:        80 (PostgreSQL)
  Failing:        0
  Skipped:        3 under SQLite only (2 RLS + 1 dense-channel test)
Frontend tests:   1 passing; production build green
Coverage:         not measured
```

## Phase 5 test inventory — `tests/api/test_retrieval.py`

| Suite | Proves |
|---|---|
| `EmbeddingProviderTests` (2) | deterministic vectors, 384 dims, L2-normalized; different texts differ |
| `ChunkingTests` (3) | chunks span pages with carried context and correct hashes; index job creates chunks+embeddings (model recorded); rerun is incremental (`created=0`, no duplicates) |
| `RevisionAwareInvalidationTests` (1) | edit ⇒ old chunks stale=true, new content indexed, hash sets disjoint, stale rows retained (§27) |
| `HybridRetrievalTests` (4) | keyword hit returns own chunk w/ snippet; bob gets zero of alice's notes; unauthenticated → 401; dense leg produces scores on PostgreSQL |
| `ReferenceBookTests` (4) | ingestion creates READY book + platform chunk (profile NULL) retrievable by users; non-READY book excluded from retrieval; ingestion idempotent per title/author |

Plus pre-existing suites from Phases 1–4 (67 tests).

## Manual E2E performed

Through the running stack against PostgreSQL: upload → OCR → automatic downstream indexing (chunk count + embeddings verified via SQL) → `/search` returns own-note hits with dense+keyword RRF scores → reference book ingested (READY) → same query surfaces the reference snippet for a *different* user while their own-notes results stay empty.

## Honest gaps

- No concurrency tests for multi-worker claim/index races.
- Dense-channel quality untested beyond "scores present" (no relevance assertions possible without real embeddings).
- RLS behavioral enforcement still untested as restricted role.
- Reference-book command lacks its own failure-path test (malformed JSON).
- Coverage unmeasured.
