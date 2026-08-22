# Testing — after Phase 2

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=2): 37 found — 35 passed, 2 skipped

# Backend — integration profile (real PostgreSQL)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests
# → OK: 37 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Current counts

```text
Backend tests:    37 total  (+20 new in Phase 2)
  Passing:        37 (PostgreSQL run)
  Failing:        0
  Skipped:        2 under SQLite settings only (PostgreSQL-only RLS tests)
Frontend tests:   1 passing (vitest smoke); production build green
Coverage:         not measured
```

## Phase 2 test inventory — `tests/api/test_canvas.py`

| Suite | Tests | Proves |
|---|---|---|
| `SessionTests` (4) | create holds initial lock (gen=1, holder=device); foreign-profile create → 403; GET returns pages; listing user-scoped | Session ownership + initial fencing state |
| `PageTests` (3) | page create with invalid generation → 409 SESSION_LOCK_LOST; duplicate page number → 422; foreign page access → 404 | Lock-gated pagination + §66 uniqueness + isolation |
| `StrokeFencingTests` (6) | valid batch creates all; replayed keys ⇒ duplicates not new rows; stale generation ⇒ 409; wrong device ⇒ 409 despite matching generation; expired lock ⇒ 409; missing client key ⇒ 422 | §4 idempotency + §5 fencing matrix |
| `HeartbeatTakeoverTests` (3) | heartbeat refreshes expiry; stale-generation heartbeat fails; takeover increments generation and fences the old device while the new one proceeds | §5 lifecycle |
| `FinalizeTests` (4) | finalize marks page immutably; finalize is idempotent (`already_finalized`); post-finalize writes → 409 REVISION_CONFLICT; finalize requires valid lock | §67 boundary as implemented |

Phase 1 suites (17 tests: auth flow, profiles/subjects isolation, constraints, idempotency keys, RLS GUC/no-leak, job claim) remain green.

## Manual E2E performed (Phase 2)

Through the Vite proxy against PostgreSQL: session create → page create → stroke push → replay (duplicates reported) → stale-generation push (409) → takeover (gen 2) → old-device write (409) → finalize → post-finalize write (409 REVISION_CONFLICT).

## Honest gaps

- True concurrent-writer races untested (SQLite ignores `select_for_update`; no PG-based concurrency suite yet).
- No automated frontend tests for the editor/outbox (manual E2E only).
- RLS behavioral enforcement still untested as a restricted role.
- No coverage measurement.
