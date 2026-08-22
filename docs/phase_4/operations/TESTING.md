# Testing — after Phase 4

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=2): 67 found — 65 passed, 2 skipped

# Backend — integration profile (real PostgreSQL)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests
# → OK: 67 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    67 total  (+7 new in Phase 4)
  Passing:        67 (PostgreSQL)
  Failing:        0
  Skipped:        2 under SQLite only (PostgreSQL-only RLS tests)
Frontend tests:   1 passing; production build green
Coverage:         not measured
```

## Phase 4 test inventory — `tests/api/test_note_space.py`

| Suite | Proves |
|---|---|
| `NoteSpaceFlowTests` (5) | POST /pdf enqueues render job that succeeds and stores a valid `%PDF-` artifact; duplicate request resolves to a single artifact; metadata endpoint shape; download returns signed URL whose GET yields PDF bytes; foreign users get 404 on artifact/download/request; renderer-version change creates a NEW artifact while retaining the old one |
| `FaithfulEditRegenerationTests` (1) | user edit ⇒ new revision ⇒ regeneration produces a distinct artifact, old retained, new bytes valid |
| `LayoutExtractionPurityTests` (1) | extraction maps line texts verbatim and propagates the explicit heading flag — renderer adds/removes nothing |

Plus pre-existing suites from Phases 1–3 (60 tests): auth, profiles/subjects isolation, constraints, idempotency keys, RLS GUC/no-leak, job claim, canvas API/fencing/finalize→ingestion.

## Manual E2E performed

Through the running stack: upload → OCR completed → edit with heading flag → revision 2 (no job) → generate PDF (202) → artifact listed (`notespace-pdf-v1`, ~15 KB) → download URL fetched → `%PDF-1.3` bytes returned → foreign-user download blocked (404).

## Honest gaps

- No test extracts PDF *text* to assert verbatim content inside the rendered file (purity asserted at the layout boundary; fpdf2 trusted beyond it).
- No visual/layout regression tests.
- RLS behavioral enforcement still untested as restricted role; coverage unmeasured.
