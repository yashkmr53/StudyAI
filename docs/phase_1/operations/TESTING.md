# Testing

## Commands (verified)

```bash
# Backend — fast unit profile (SQLite :memory:, MD5 hasher, eager Celery)
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests
# → OK (skipped=2) — 17 found: 15 passed, 2 skipped

# Backend — integration profile (real PostgreSQL; RLS/GUC tests execute)
cd backend
DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests
# → OK — 17 passed, 0 skipped

# Frontend
cd frontend
npm test          # vitest → 1 file, 1 test, passed
npm run build     # tsc -b strict type-check + production build
```

## Current counts

```text
Backend tests:    17 total
  Passing:        17 (PostgreSQL run)
  Failing:        0
  Skipped:        2 under SQLite settings only (PostgreSQL-only RLS tests)
Frontend tests:   1 passing (vitest smoke)
Coverage:         not measured — no coverage tooling configured
```

## Test inventory

### API tests — `tests/api/`

| Test | File | Proves |
|---|---|---|
| `test_register_creates_user_profile_and_tokens` | `test_auth_flow.py` | Registration atomically creates user + default profile + token pair |
| `test_register_rejects_short_password_with_error_envelope` | same | §61 envelope on validation failure incl. `req_` request id |
| `test_register_is_idempotent_per_email` | same | Duplicate email → 422 |
| `test_login_returns_tokens` | same | Login issues tokens |
| `test_logout_blacklists_refresh_token` | same | Logout blacklists; replayed refresh → 401 |
| `test_unauthenticated_request_uses_envelope` | same | 401 envelope shape |
| `test_create_and_list_subject_scoped_to_profile` | `test_profiles_subjects.py` | Subject create + ownership-scoped listing |
| `test_cannot_create_subject_in_foreign_profile` | same | Foreign profile → 403 FORBIDDEN |
| `test_profiles_listing_is_isolated_between_users` | same | Cross-user listing isolation |
| `test_duplicate_subject_name_rejected_per_profile` | same | Unique constraint surfaces as 422 |
| `test_subject_requires_known_profile` | same | Unknown profile → 422 |

### Unit/integration tests — `tests/unit/test_shared.py`

| Test | Proves |
|---|---|
| `IdempotencyKeyTests` | Key formats match spec §20 exactly |
| `RLSContextTests::test_set_profile_context_binds_transaction_local_guc` | GUC visible inside transaction (PG only) |
| `RLSContextLeakIntegrationTests` (TransactionTestCase) | Context does **not** leak after commit (PG only) |
| `JobModelTests::test_claim_is_atomic_single_winner` | Conditional claim: one winner, attempt_count=1 |

### Model constraint tests

`ModelConstraintTests` — DB-level unique constraints fire for Profile `(user,name)` and Subject `(profile,name)`.

## What is NOT tested (honest gaps)

- RLS *enforcement* against a non-superuser role (policies verified structurally via `pg_policies`, not behaviorally).
- No concurrency tests beyond the single-SQL-statement job claim.
- No offline-sync runtime tests (no transport exists).
- No E2E browser automation; the auth flow was verified manually through the Vite proxy.
- No AI tests (nothing to test).
- No coverage measurement.

## Conventions for new tests

1. Every endpoint ships with happy path + authorization failure + validation failure + envelope assertions.
2. Postgres-only behavior goes in tests that skip gracefully under SQLite and run under dev settings.
3. Business logic is tested at the service layer (`shared/*` pattern), independent of views.
