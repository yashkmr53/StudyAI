# Test Baseline Investigation — Docker Run vs GitHub Actions

Date/time: 2026-08-22 ~14:07–14:21 UTC
Mode: investigation only. No application code, tests, CI config, or throttling behavior was changed. Nothing committed or pushed.

---

## 1. Environment Used

| Aspect | Value |
| --- | --- |
| Runtime | Docker Compose stack (`api`, `db`, `redis`, `worker`, `frontend`) — all healthy before the run |
| Settings module inside `api` | `config.settings.prod` (container env), **not** `config.settings.test`/`ci` |
| Database used by tests | PostgreSQL `test_studyai` (created/destroyed by the runner from prod DB config) |
| Effective key settings | `RATE_LIMITING_ENABLED=True`, `CELERY_TASK_ALWAYS_EAGER=False`, `CACHES` unset → `LocMemCache`, throttle rate `auth: 30/min` |

## 2. Exact Command

```bash
docker compose exec -T api python manage.py test tests --noinput -v 2
```

Full output saved locally to `docker-test-run.log` (outside the repo).

## 3. Result Summary

| Metric | Value |
| --- | --- |
| Total tests | 116 |
| Failures | 77 |
| Errors | 2 |
| Passed | 37 |
| Exit code | 1 |
| Duration | 3.065 s (unittest); ~5 s wall clock |

This exactly reproduces the previously observed local baseline (116 / 77 / 2).

## 4. Failure Categories

79 failing/erroring blocks decompose into exactly two root causes:

### Category A — Throttling cascade: 75 of 79

74 blocks contain an explicit `RATE_LIMITED` response body; one more
(`test_register_writes_audit_entry`: `429 != 201`) asserts against a throttled register call.
Typical signature (in `setUp`, via `tests/api/utils.py::authenticated_client`):

```text
AssertionError: b'{"error":{"code":"RATE_LIMITED","message":"Request was throttled.
Expected available in 59 seconds.", ...}}'
```

### Category B — Non-eager Celery under prod settings: 4 of 79

`EnrichmentFlowTests.test_edit_marks_enrichment_ai_stale` (ERROR),
`EnrichmentFlowTests.test_enrich_end_to_end_creates_verified_note` (FAIL),
`EnrichmentFlowTests.test_second_enrich_returns_existing_note` (FAIL),
`RefreshAiTests.test_refresh_creates_new_generation_retaining_old` (ERROR).
Signatures: `note` is `None`, `EnrichedNote.DoesNotExist`, `0 != 1`.

## 5. First / Root Failure & Cascades

- **First failure in execution order** was NOT a 429: `EnrichmentFlowTests.test_edit_marks_enrichment_ai_stale` failed immediately at suite start (Category B), because its setUp ran before the throttle bucket filled.
- The auth-throttle budget (30 requests/min) is then consumed by early test classes (each two-client setUp costs 4 auth hits: register+login × alice+bob; DB rolls back between tests so users are recreated every time). Within seconds every subsequent `authenticated_client()` call — i.e., nearly every remaining API test's setUp — receives 429. That is the dominant cascade: **one saturated bucket → ~75 downstream failures**.
- The 4 Category-B failures are independent of throttling (see §8b).

No PostgreSQL, migration, RLS, connectivity, missing-env-var, or fixture problems were found. The database initialized cleanly (`test_studyai` created, migrations applied, unit/RLS tests passed).

## 8a. Authentication/Throttle Findings (Category A)

| Question | Finding |
| --- | --- |
| Throttle class | `LiveSettingsScopedRateThrottle` (`backend/shared/throttles.py`), subclass of DRF `ScopedRateThrottle`; reads rates live and returns `None` (never throttle) when `settings.RATE_LIMITING_ENABLED` is false |
| Scope | `"auth"` on Register/Login/Logout/PasswordReset views |
| Rate in this run | `30/min` (from `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']` via prod settings) |
| Cache backend | Default `LocMemCache` (no `CACHES` override in prod/base) |
| State shared between tests? | **Yes — single bucket** `throttle_auth_127.0.0.1`. Django test client always presents `REMOTE_ADDR=127.0.0.1`, verified live |
| Persists between individual tests? | **Yes.** Django `TestCase` isolates the database per test but does **not** clear the cache; only `test_hardening.py` calls `cache.clear()` and deliberately re-enables throttling with its own cache override |
| Redis involved? | No — the throttle cache is in-process LocMemCache. Redis is unrelated to throttling |
| Does Django test isolation reset state? | DB: yes. Throttle counters: no |
| Window relevance | Whole suite finishes in ~3 s ≪ 60 s sliding window → history never expires mid-run |

Design intent (per `config/settings/test.py` comments): throttling disabled by default
(`RATE_LIMITING_ENABLED=False`, `DummyCache`) and enabled per-test via overrides.
Running the suite under `config.settings.prod` violates that assumption.

## 8b. Celery Finding (Category B)

Under prod settings `CELERY_TASK_ALWAYS_EAGER=False`. The enrich endpoint enqueues
`process_job_task` through `transaction.on_commit`; `captureOnCommitCallbacks(execute=True)`
executes the enqueue — sending the job to the **real Redis broker**, where the separate
live worker consumed it against the **wrong database** (`studyai`, not `test_studyai`).
Evidence: worker logs show `Task apps.jobs.tasks.process_job_task[...] received`
21 times during the test window. No `EnrichedNote` is ever created inside the test
process, so assertions on note rows fail regardless of throttling.
`config/settings/ci.py` sets `CELERY_TASK_ALWAYS_EAGER=True`, which is why these
tests are not affected on GitHub Actions.

## 9. Docker vs GitHub Comparison

Known GitHub symptoms: DB + migrations OK; 116 tests discovered; initial registration
passes; later tests get 429 from `/api/v1/auth/register`; explicit throttle test passes.

| Mechanism | Docker (prod settings) | GitHub (ci.py) |
| --- | --- | --- |
| `RATE_LIMITING_ENABLED` / cache | True / LocMemCache → shared bucket | True (inherited from base) / LocMemCache → same shared-bucket mechanism |
| Eager Celery | False → enrichment tests also break | True → enrichment tests unaffected |
| Explicit throttle test | Passes (self-managed cache + clear) | Passes (same reason) |

Verdict for the **429 failures specifically**: **same root cause as GitHub Actions** —
throttling left enabled for tests because neither `ci.py` nor the prod-settings
Docker environment applies the test-intended `RATE_LIMITING_ENABLED=False` /
cache-isolation configuration.

Verdict for the **complete Docker baseline**: **multiple independent root causes**
(throttle mismatch **plus** non-eager-Celery settings mismatch). GitHub exhibits only
the throttle problem.

## 10. Files Inspected (read-only)

`docker-compose.yml` · `.env` (key presence only, values never read/printed) ·
`backend/config/settings/{base,dev,test,ci,prod}.py` · `backend/shared/throttles.py` ·
`backend/apps/accounts/views.py` · `backend/tests/api/{utils.py,test_auth_flow.py,test_ai_classroom.py,test_hardening.py}` ·
`backend/apps/jobs/tasks.py` · `.github/workflows/ci.yml` · worker container logs

## 11. Commands Executed

```bash
docker compose ps
docker compose exec api printenv                      # env keys only
docker compose exec api python manage.py test tests --noinput -v 2   # the baseline run
docker compose exec api python -c ...                 # effective settings introspection
docker compose exec api python -c ...                 # DRF throttle key format / test REMOTE_ADDR
docker compose logs worker --since ...                # broker activity during test window
```

## 12. Assumptions

1. The GitHub result referenced is current and accurately summarized (DB OK, 116 discovered, early pass → later 429, throttle test passes).
2. Running the suite under `config.settings.prod` is accidental, not intended — evidenced by the existence and documented intent of `config.settings.test.py`.
3. The historical local "116/77/2" run used the same command/environment (numbers match exactly).

## 13. Recommended Next Step (NOT implemented — awaiting approval)

Run the suite in Docker against CI-shaped settings instead of prod:

```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.ci api python manage.py test tests --noinput -v 2
```

Expected effect: fixes Category B fully (eager tasks). Category A needs the
test-design intent applied to whatever settings module is chosen for Docker runs
(`RATE_LIMITING_ENABLED=False` + cache isolation by default, throttling exercised
only where tests opt in) — mirroring what `config/settings/test.py` already encodes,
while keeping production throttling untouched.

Decision needed from maintainer before any change: which settings module should be
canonical for Docker-hosted test runs (`ci.py` extended, a new `docker_test.py`, or `test.py` switched to Postgres).

---

# Test Settings Configuration Investigation (Phase 8)

Date/time: 2026-08-22 ~14:25–14:45 UTC. Investigation only — no files edited except this document.

## What was tested / what happened

1. **CI-settings Docker run (user-executed, reported):** `DJANGO_SETTINGS_MODULE=config.settings.ci`
   inside the api container → same `RATE_LIMITED` cascade in `authenticated_client()` setUp.
   Proves: `ci.py` fixes the Celery half (Category B) but **not** the throttle half (Category A),
   because it inherits `RATE_LIMITING_ENABLED=True` and LocMemCache from `base.py`.
2. **SQLite run under `config.settings.test` (agent-executed, read-only):**
   `docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.test api python manage.py test tests --noinput`
   → **116 tests, OK, 3 skipped, exit 0, 2.2 s.**
   Proves: application code and all tests are healthy; every failure in the earlier
   prod/ci runs was environmental. Also proves the suite is fully SQLite-compatible
   by design (vendor-guarded RLS/pgvector migrations; `AdaptiveVectorField` degrades gracefully).
3. The 3 SQLite skips are exactly the PostgreSQL-only coverage:
   `dense_channel_used_on_postgresql`, plus 2 × `RLS context requires PostgreSQL`.

## Settings comparison (effective values)

| Dimension | base.py | prod.py | ci.py | test.py |
| --- | --- | --- | --- | --- |
| DEBUG | `False` | forced `False` | forced `False` | forced `False` |
| Database | hardcoded PG `studyai@/tmp` socket (host-dev legacy; unused by other modules) | PG, env-driven, sslmode default `require` | PG, env-driven, defaults `studyai_test@localhost` | **sqlite `:memory:` only — no env hook** |
| PostgreSQL features | — | full (pgvector, RLS) | full | migrations no-op on sqlite; 3 PG-only tests skip |
| `ALLOWED_HOSTS` | `[]` | env comma-split | `["*"]` | inherits `[]` (Django test env auto-adds `testserver`) |
| `RATE_LIMITING_ENABLED` | `True` | `True` ← **root cause A** | `True` ← GH cascade | `False` (per-test opt-in) |
| `CACHES` | unset → LocMemCache | same (shared bucket across tests) | same | `DummyCache` (no state leakage) |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | `False` ← **root cause B** | `True` | `True` |
| Celery broker | settings attr hardcoded `redis://localhost:6379/0` (**dead value**) | effective broker = `redis://redis:6379/0` from env var via Celery layer (verified `app.conf.broker_url` in both containers) | inherits dead attr; irrelevant (eager) | `memory://` |
| REST framework | JWT default auth, `IsAuthenticated` default, rates auth 30/min · ai 120/min · user 600/min | inherited | inherited | inherited + `TEST_REQUEST_DEFAULT_FORMAT=json` |
| Password hashing | Argon2-first (slow) | same | MD5 (fast) | MD5 (fast) |
| RLS | via vendor-guarded migrations + GUC context service | active | active | inert on sqlite |
| Object storage | local, `BASE_DIR/var/objectstore` | env-wired | inherited | inherited |
| Prevents correct test runs? | DB block unusable in-container (but overridden everywhere) | throttling + non-eager tasks | throttling | nothing — but forfeits PG-only coverage |

Latent finding (flagged, not fixed): `settings.CELERY_BROKER_URL` is hardcoded while the
compose env var of the same name actually drives Celery at runtime. Production currently
works through the env path; aligning the settings attribute is an optional future hardening item.

## Can `test.py` run the COMPLETE suite against Docker PostgreSQL?

**Not without modification.** Its `DATABASES` is hardcoded to SQLite `:memory:` with no
environment hook, so pointing it at the Docker `db` service is impossible as-is.
Everything else about it is migration-safe on PostgreSQL (all RLS/pgvector migrations are
vendor-guarded), so a Postgres-wired variant would run all 116 tests including the 3
currently skipped ones.

## GitHub Actions configuration (exact)

`.github/workflows/ci.yml` (backend job):
- Service container: `pgvector/pgvector:pg16` (ephemeral `studyai_test` database, CI-inline credentials).
- Env: `DJANGO_SETTINGS_MODULE=config.settings.ci`, `POSTGRES_HOST=localhost`,
  `POSTGRES_PORT=5432`, `POSTGRES_DB=studyai_test`.
- Steps: install deps → `manage.py check` → `makemigrations --check --dry-run` →
  `manage.py test tests --noinput -v 2`.

GitHub therefore exercises **PostgreSQL + pgvector + RLS with eager Celery**, and fails
only on the throttle cascade — exactly matching the Category-A signature.

## Architectural options

| | A: use `test.py` in Docker | B: new `docker_test.py` | **C: extend `ci.py` (recommended)** | D1: env-switchable `DATABASES` in `test.py` |
| --- | --- | --- | --- | --- |
| PostgreSQL coverage | ❌ sqlite only (3 skips) | ✅ if wired to PG | ✅ full | ✅ optional |
| Celery correctness | ✅ eager | ✅ | ✅ already eager | ✅ |
| Throttling behaves correctly | ✅ off-by-default | depends on authorship | ✅ off-by-default after 2-line change | ✅ |
| Production untouched | ✅ | ✅ | ✅ | ✅ |
| GitHub shares config | ⚠️ would downgrade GH to sqlite | ❌ second module to maintain | ✅ same module, same fix | ⚠️ changes GH silently |
| Duplication risk | none new | high (clone of ci.py) | none | medium |

Why C wins: the failure class we just diagnosed was *configuration divergence*;
B adds another divergent copy. C makes GitHub and Docker share one truthful,
PG-exercising test configuration with a two-line diff, and it codifies what the
codebase already documents as intent ("throttling disabled by default; enabled
per-test via `override_settings`").

## Throttle-test inspection (requirement 7)

`tests/api/test_hardening.py::RateLimitTests` demonstrates the intended pattern and is
unaffected by the recommended change:
- `@override_settings(REST_FRAMEWORK={...rates: auth 3/min...}, CACHES={LocMemCache}, RATE_LIMITING_ENABLED=True)`
- `tearDown`: `cache.clear()`
- Asserts login returns 429 with `RATE_LIMITED` envelope after threshold, and that
  `/healthz` stays unthrottled.

i.e., real throttling remains exercised deliberately, with tight rates, isolated state.

## Exact commands executed this phase (read-only)

```bash
cat backend/apps/retrieval/migrations/0000_pgvector_extension.py
cat backend/apps/documents/migrations/0002_enable_rls.py
grep -n Vector backend/apps/retrieval/models.py
sed -n 40,110p backend/tests/api/test_hardening.py
docker compose exec -T api python -c "...settings introspection..."      # ×3
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test api python manage.py test tests --noinput   # sqlite proof
docker compose logs worker --since ...                                    # broker receipts
grep -rn CELERY_BROKER backend --include="*.py"
```

## Status

No source, test, CI, compose, or settings file was modified. Nothing committed or pushed.
Only `docs/test-baseline-investigation.md` (this document) was updated.

---

# Remediation (Phase 8 — Approved Option C)

Date/time: 2026-08-22 ~16:00–16:20 UTC. Scope approved by maintainer before implementation.

## Complete history

```text
Baseline (116 tests: 77F / 2E under prod settings in Docker)
  → Root-cause investigation (Category A: throttle cascade ×75; Category B: non-eager Celery ×4)
  → CI-settings reproduction (user run: Category B fixed, Category A persisted)
  → Test-settings comparison (test.py passes fully on SQLite but skips 3 PG-only tests;
    ci.py keeps PG coverage; Option C selected — extend ci.py by two lines)
  → APPROVED remediation
  → Implementation + verification (below)
```

## Implementation

`backend/config/settings/ci.py` — exactly two additions after the existing eager-Celery line:

```python
RATE_LIMITING_ENABLED = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache"
    }
}
```

Nothing else changed: `prod.py`, `base.py`, `test.py`, application code, tests,
throttle rates, `docker-compose.yml`, and the GitHub workflow are untouched.

Operational note discovered during verification: `docker compose exec` runs against the
image-baked copy of the code. The first post-edit suite run still showed the throttle
cascade because the container predated the edit (`grep RATE_LIMITING_ENABLED config/settings/ci.py`
→ not found inside container). Rebuilt backend images (`docker compose build api worker && docker compose up -d`)
to load the already-approved change, then re-ran. No further code/config changes were made.

## Verification results

Command:

```bash
docker compose exec -e DJANGO_SETTINGS_MODULE=config.settings.ci api python manage.py test tests --noinput -v 2
```

| Metric | Before remediation | After remediation |
| --- | --- | --- |
| Total tests | 116 | 116 |
| Passed | 37 | **116** |
| Failures | 77 | **0** |
| Errors | 2 | **0** |
| Skipped | 0 (3 skipped only on SQLite runs) | **0** |
| Exit code | 1 | **0** |
| Duration | ~3 s | 3.94 s unittest / 6 s wall |

### Category checks

- **A. Registration no longer receives unexpected 429s:** zero `RATE_LIMITED` occurrences in the full-suite log.
- **B. Celery enrichment tests execute successfully:** `EnrichmentFlowTests` and `RefreshAiTests`
  all pass with inline execution (log shows real enrichment output, e.g. "2 blocks (1 verified)");
  no tasks leaked to the live broker.
- **C. PostgreSQL-only tests execute:** `test_dense_channel_used_on_postgresql`,
  `test_set_profile_context_binds_transaction_local_guc`,
  `test_context_does_not_leak_after_commit` — all ran (not skipped) and passed on Docker Postgres.
  Summary line is plain `OK` with no skip count.
- **D. RateLimitTests still pass:** standalone run of
  `tests.api.test_hardening.RateLimitTests` → `Ran 2 tests ... OK`, proving the throttle
  machinery itself remains functional when explicitly opted in.

### Production separation confirmed (live introspection of running stack)

```text
prod RATE_LIMITING_ENABLED: True
prod auth rate:             30/min
prod CACHES:                LocMemCache
prod CELERY_TASK_ALWAYS_EAGER: False
```

Final separation achieved:

```text
PRODUCTION            : real rate limiting · LocMemCache · non-eager Celery
CI / DOCKER TESTS     : PostgreSQL + pgvector · eager Celery · throttling off by default ·
                        explicit opt-in throttle tests
```

## Post-remediation git checks

- `git diff --check` → clean (no whitespace/conflict-marker issues).
- Only file modified for this remediation: `backend/config/settings/ci.py`.
- Documentation updated: this document plus the "Running the Test Suite" section in
  `docs/docker-development-environment.md`.
- Nothing committed or pushed.

## Remaining known items (not part of this remediation)

1. Latent wiring quirk: Django's `settings.CELERY_BROKER_URL` attribute is a hardcoded
   `localhost` value that nothing reads at runtime; the compose env var drives Celery via
   its own configuration layer. Aligning it is optional future hardening.
2. The canonical Docker-test command requires the explicit `-e DJANGO_SETTINGS_MODULE=...`
   override until/unless a compose-level test profile is introduced.
3. Repo hygiene from earlier phases still open: initial commit state, legacy `myenv/`,
   `studyai_backup.sql`, `backups/`.

---

# Canonical Test Wrapper Remediation (Phase 8 — scripts/test.sh)

Date/time: 2026-08-22 ~16:40–17:10 UTC. Scope approved by maintainer before implementation:
canonical developer test command, CI alignment, production smoke validation, documentation.

## Goal

`./scripts/test.sh` → Docker PostgreSQL/pgvector → deterministic test settings → all
tests pass, while production keeps real throttling, real Celery, and its security posture.

## Files inspected (Phase 1)

`backend/config/settings/{base,dev,test,ci,prod}.py` · `backend/shared/throttles.py` ·
`backend/apps/accounts/views.py` · `backend/tests/api/{test_hardening.py,utils.py}` ·
`.github/workflows/ci.yml` · `docker-compose.yml` · `backend/Dockerfile` · `backend/.dockerignore` ·
`backend/manage.py` · `backend/config/{urls.py,celery.py}` · `backend/shared/observability/views.py` ·
`docs/{docker-development-environment.md,test-baseline-investigation.md}` · `.env.example`.

## Architectural decisions

1. **`config.settings.ci` stays the single canonical test configuration.** It already
   contained the approved values (PostgreSQL env-driven, MD5 hasher,
   `CELERY_TASK_ALWAYS_EAGER=True`, `RATE_LIMITING_ENABLED=False`, `DummyCache`);
   verified live inside the container. No new settings module introduced (avoids a third
   divergent copy).
2. **Root-level `scripts/test.sh` chosen over a Makefile** as the one developer-facing
   entry point (matches the plan's preferred option; zero extra tooling).
3. **The wrapper pins `DJANGO_SETTINGS_MODULE=config.settings.ci` itself** — developers
   never type it. The compose default (`config.settings.prod`) is intentionally left
   untouched: runtime containers keep prod behavior.
4. **Stale-image guard**: `docker compose exec` runs image-baked code (documented earlier
   incident). Before testing, the script compares a sha256 over every backend `.py`
   (excluding `var/`, `__pycache__/`, `.pytest_cache/`) between `/app` in the image and
   the host tree mounted read-only at `/src`, computed by ONE throwaway container from
   the api image itself — docker-only, no host Python required. Mismatch ⇒ hard failure
   with rebuild instructions.
5. **Failure policy**: missing Docker/.env/stopped services ⇒ clear fix-it message and
   exit 1. No auto-starting (would need secrets and could surprise), no volume deletion.
6. **GitHub Actions unchanged functionally**: already runs the same underlying command
   (`python manage.py test tests --noinput -v 2`) under the same settings module against
   a pgvector service container. Added only a cross-reference comment to prevent drift.
7. **Production smoke = small dedicated script (`scripts/smoke_prod.sh`)** reusing existing
   pieces (`manage.py check`, `/healthz`, `/readyz`, password-reset probe, celery inspect
   ping). No new test framework; the full suite is never run against prod services/data;
   probes write nothing.

## Files changed

| File | Change |
| --- | --- |
| `scripts/test.sh` | NEW — canonical wrapper: preflight checks, stale-image guard, pins ci settings, execs suite; label passthrough |
| `scripts/smoke_prod.sh` | NEW — production-configuration smoke validation |
| `.github/workflows/ci.yml` | comment-only cross-reference above the test step |
| `docs/docker-development-environment.md` | canonical command section rewritten; "do not use" warning; smoke section; troubleshooting rows; setup summary |
| `docs/test-baseline-investigation.md` | this journal |
| `backend/config/settings/ci.py` | NOT changed this session (carried uncommitted diff from the previously approved remediation) |

## Failures encountered & fixes

- **Smoke throttle probe initially saw no 429 after 32 requests.** Root cause: gunicorn
  runs 3 workers and LocMemCache counters are per-process, so ~32 requests split ~11 per
  worker — below the per-process 30/min bucket. Fix: probe loops (≤120 no-write requests)
  until some worker's bucket fills, then asserts first-call `202` + later `429`.
  Recorded as a known production nuance (per-process throttle accounting with multiple
  workers); production configuration deliberately left unchanged.

## Verification results

| Command | Result |
| --- | --- |
| `./scripts/test.sh` | Ran 116 tests — OK, 0 failures, 0 errors (PostgreSQL `test_studyai` created/destroyed) |
| `./scripts/test.sh tests.api.test_hardening.RateLimitTests` | Ran 2 tests — OK (real 429/RATE_LIMITED assertions intact) |
| `./scripts/test.sh tests.unit.test_shared.RLSContextTests tests.unit.test_shared.RLSContextLeakIntegrationTests tests.api.test_retrieval.HybridRetrievalTests.test_dense_channel_used_on_postgresql` | Ran 3 tests — OK (RLS GUC + pgvector dense channel on PostgreSQL) |
| `./scripts/test.sh tests.api.test_ai_classroom.EnrichmentFlowTests tests.api.test_ai_classroom.RefreshAiTests` | Ran 5 tests — OK (eager Celery, inline execution) |
| Direct underlying command `docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.ci api python manage.py test tests --noinput -v 2` | Ran 116 tests — OK, identical to wrapper output |
| Effective ci settings introspection (in-container) | `RATE_LIMITING_ENABLED=False`, `CELERY_TASK_ALWAYS_EAGER=True`, DummyCache, PostgreSQL engine |
| `./scripts/smoke_prod.sh` | ALL CHECKS PASSED (prod flags PASS ×4, healthz/readyz 200, auth 202→429, worker pong) |
| Stale-guard negative test (temporary stray file) | exit 1 with rebuild instructions; guard then cleaned up |
| Services-down negative test (`compose stop api`) | exit 1 with start instructions; stack restarted healthy |

## Assumptions

1. Compose v2 syntax (`docker compose ps --services --status running`, `run --rm --no-deps`).
2. Host bash available (macOS/Linux); Windows contributors use WSL/Docker Desktop shell.
3. Tests never require the frontend/worker/redis services running (eager Celery +
   DummyCache make redis irrelevant to the suite).

## Production separation re-confirmed

Smoke run on the same machine, same moment:

```text
PROD : rate_limiting_enabled=True · auth 30/min · LocMemCache · CELERY_TASK_ALWAYS_EAGER=False
       /healthz 200 · /readyz 200+DB · password-reset 202→429 · celery worker pong
CI   : RATE_LIMITING_ENABLED=False · DummyCache · CELERY_TASK_ALWAYS_EAGER=True · PostgreSQL/pgvector
```

## Remaining known items

1. Latent wiring quirk: Django's `settings.CELERY_BROKER_URL` attribute is a hardcoded
   `localhost` value that nothing reads at runtime; the compose env var drives Celery via
   its own configuration layer. Aligning it is optional future hardening.
2. NEW nuance (documented, not changed): DRF throttling counters are per-process under
   LocMemCache, so multi-worker deployments enforce N×rate per client IP unless the cache
   backend is moved to Redis/Memcached.
3. Repo hygiene from earlier phases still open: legacy `myenv/`, `studyai_backup.sql`,
   `backups/`.

Nothing committed or pushed.
