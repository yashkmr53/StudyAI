# Testing — final counts after Phase 8

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=3): 116 found — 113 passed, 3 skipped

# Backend — integration profile (real PostgreSQL: dense + RLS execute)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests --noinput
# → OK: 116 passed, 0 skipped

# Frontend
cd frontend && npm test && npm run build
```

## Counts

```text
Backend tests:    116 total  (+15 new in Phase 8)
  Passing:        116 (PostgreSQL) / 113 + 3 skips (SQLite)
  Failing:        0
Frontend:         vitest 1/1; production build green
Coverage:         not measured
```

## Phase 8 test inventory — `tests/api/test_hardening.py` (12 new)

| Suite | Proves |
|---|---|
| `HealthEndpointsTests` (2) | /healthz open liveness; /readyz DB probe; security headers present |
| `StatusEndpointTests` (2) | staff status payload contains jobs/providers/citations/requests sections incl. queue depth, dead-letter count, p95; non-staff 403 |
| `RateLimitTests` (2) | auth scope throttles to 429 RATE_LIMITED envelope after limit (LocMem cache override); non-throttled paths unaffected |
| `MagicByteTests` (2) | declared-type mismatch → 422; PNG magic-byte mismatch → 422 even with correct header |
| `BudgetTests` (1) | daily AI budget exhaustion ⇒ chat message 429 RATE_LIMITED (graceful degradation) |
| `LLMFallbackChainTests` (1) | failing primary → mock fallback succeeds; attempted chain recorded |
| `AuditLogTests` (3) | register/login/logout write audit entries; staff-only listing (403 for regular users) |

Plus the pre-existing 104 tests from Phases 1–7.

## Manual E2E performed

Backup drill (`backup_database` → `verify_backup`: dump 159,790 bytes restored into scratch DB with matching row counts) and load baseline via `scripts/load_test.py` — all scenarios p95 < 500 ms against the dev server.

## Honest gaps

- CI workflow authored but never executed on GitHub.
- No concurrency/race suite on PostgreSQL for job claiming under parallelism.
- Coverage unmeasured.
