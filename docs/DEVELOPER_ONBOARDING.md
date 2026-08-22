# StudyAI Developer Onboarding

Welcome! This guide takes you from a fresh clone to a fully running local
StudyAI stack — including your own admin account and a green test suite —
without needing any passwords or credentials from another developer.

Everything runs in **Docker**. You do not install Python, PostgreSQL, Redis,
Node.js, nginx, or Django on your machine.

---

## 1. Prerequisites

Install exactly two things:

| Tool | Why | Get it from |
| --- | --- | --- |
| **Git** | Clone the repository, commit your work | https://git-scm.com (macOS: `xcode-select --install`) |
| **Docker Desktop** (or Docker Engine + Compose v2) | Runs the entire StudyAI stack | https://www.docker.com/products/docker-desktop |

That is all. The repository's own rule is:

> The host machine needs exactly two things installed: Docker Desktop and git.
> No virtualenv, no local Postgres, no local Redis.

What runs inside Docker instead of your host:

| Component | Where it runs |
| --- | --- |
| PostgreSQL 16 + pgvector | container (`db`) |
| Redis 7 | container (`redis`) |
| Django API (gunicorn) | container (`api`) |
| Celery worker | container (`worker`) |
| React PWA + nginx reverse proxy | container (`frontend`) |

One optional host convenience: any Python 3 for generating secret values in
step 3. If you do not have it, step 3 shows a Docker-only alternative.

Before continuing, make sure Docker Desktop is running (whale icon in your
menu bar / system tray).

---

## 2. Clone the Repository

HTTPS (works everywhere, prompts for your GitHub credentials):

```bash
git clone https://github.com/yashkmr53/StudyAI.git
cd StudyAI
```

SSH (if you have added an SSH key to your GitHub account):

```bash
git clone git@github.com:yashkmr53/StudyAI.git
cd StudyAI
```

> Note: existing contributors may have a remote like
> `git@github-personal:yashkmr53/StudyAI.git` — that `github-personal` part is
> a personal SSH alias configured in their own `~/.ssh/config`. Use whichever
> standard form works for you; both point at the same repository.

---

## 3. Configure Local Environment

All local configuration lives in `.env` at the repository root. It is
git-ignored (check `.gitignore`) and must **never** be committed or shared.

```bash
cp .env.example .env
```

Now open `.env` in an editor and fill in values. Every developer generates
their OWN secrets — never reuse someone else's, never copy them from chat.

### Which variables matter

| Variable | What it is | What to set |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | Settings file containers load | Leave as `config.settings.prod` (the project's supported local setup; safe dev overrides below) |
| `DJANGO_DEBUG` | Debug pages on/off | Keep `0` (gunicorn-safe) |
| `DJANGO_SECRET_KEY` | Signs sessions/CSRF/signed URLs (**application secret**) | Generate your own (below) |
| `DJANGO_ALLOWED_HOSTS` | Hostnames Django answers | Keep `localhost,127.0.0.1` |
| `DJANGO_SECURE_SSL_REDIRECT` / `DJANGO_SESSION_COOKIE_SECURE` / `DJANGO_CSRF_COOKIE_SECURE` / `DJANGO_HSTS_SECONDS` | HTTPS-only hardening flags | Keep the `=0` values for plain-HTTP localhost; they are `=1` defaults in real deployments |
| `POSTGRES_DB` / `POSTGRES_USER` | Database name/role created on first start | Keep defaults (`studyai` / `studyai`) |
| `POSTGRES_PASSWORD` | Password between Django and Postgres (**machine-to-machine credential**, not a human login) | Generate your own (below) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | How containers reach Postgres | Keep `db` / `5432` (Docker network names) |
| `POSTGRES_SSLMODE` | TLS for DB traffic | Keep `disable` (traffic stays inside the private Docker network) |
| `CELERY_BROKER_URL` | Redis broker address for background jobs | Keep `redis://redis:6379/0` |
| `OBJECT_STORAGE_BACKEND`, `OBJECT_STORAGE_LOCAL_DIR`, `SIGNED_URL_TTL_SECONDS` | Upload storage settings | Defaults are fine locally |
| `OCR_API_KEY`, `LLM_API_KEY`, `EMBEDDING_MODEL_PATH` | External AI providers (reserved for later phases) | Optional placeholders; leave as-is unless instructed otherwise |

### Generating your own secrets

If you have Python 3 on your host:

```bash
# Django SECRET_KEY (long random string):
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# PostgreSQL password:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Docker-only alternative (no host Python needed):

```bash
docker run --rm python:3.14-slim python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste each generated value into the matching `.env` line yourself. Tooling will
never write secrets into files for you.

### The four kinds of "credentials" here

1. **PostgreSQL password** — application↔database credential. Machines use it,
   humans never type it.
2. **Django SECRET_KEY** — application secret for cryptographic signing.
   Also not a login password.
3. **Django admin password** — YOUR personal browser login for `/admin/`,
   created interactively in step 6. It lives only in your head, never in
   `.env` or the repo.
4. **API/provider keys** — optional placeholders for future external services.

---

## 4. Start StudyAI with Docker

From the repository root:

```bash
docker compose up -d --build
```

The first run builds images and takes several minutes; later starts are fast.

What this starts (service names are exactly these):

| Service | Image / role | Notes |
| --- | --- | --- |
| `db` | `pgvector/pgvector:pg16` | PostgreSQL with the pgvector extension for AI embeddings |
| `redis` | `redis:7-alpine` | Message broker for background jobs |
| `api` | built from `backend/` | Django served by gunicorn; on every start it collects static files and applies migrations automatically |
| `worker` | same image as `api` | Celery worker consuming background jobs |
| `frontend` | built from `frontend/` | nginx serving the React app and proxying `/api/`, `/admin/`, `/static/`, `/healthz`, `/readyz` to the api |

Only **port 80** is published to your machine. Postgres (5432), Redis (6379)
and gunicorn (8000) are internal to the Docker network.

`docker compose up` **is** the normal application runtime. There is no
host-side server process in this project.

---

## 5. Verify the Environment

```bash
docker compose ps
```

A healthy stack looks like this (give the first start ~30–60 s):

```text
NAME                 SERVICE    STATUS
studyai-api-1        api        Up X minutes (healthy)
studyai-db-1         db         Up X minutes (healthy)
studyai-frontend-1   frontend   Up X minutes (healthy)
studyai-redis-1      redis      Up X minutes (healthy)
studyai-worker-1     worker     Up X minutes
```

Statuses may briefly show `(health: starting)` right after `up` — that is the
defined grace period, not an error.

Two HTTP health endpoints exist (verified routes, proxied through nginx):

| Endpoint | Meaning |
| --- | --- |
| `http://localhost/healthz` | **Liveness** — the Django process is up. Returns `{"status": "ok"}`. |
| `http://localhost/readyz` | **Readiness** — liveness plus a live database roundtrip. Returns `"database": true`; HTTP 503 if the DB check fails. |

Quick check from any terminal:

```bash
curl http://localhost/healthz
curl http://localhost/readyz
```

---

## 6. Create a Local Django Admin User

Every developer creates their OWN admin account. There is deliberately no
shared account and no documented password anywhere in this repository.

```bash
docker compose exec api python manage.py createsuperuser
```

Because this project logs in by email (the user model's username field is
`email`), Django will prompt you interactively for:

1. **Email address** — yours, e.g. `you@example.com`
2. **Password**
3. **Password (again)** — confirmation

You type the password directly into the terminal; it is not echoed and is
never stored in `.env`, Git, or this documentation.

Forgot it later? Re-run the same command with the same email and Django offers
to reset that user's password, or use:

```bash
docker compose exec api python manage.py changepassword your-email@example.com
```

---

## 7. Access StudyAI

All of the following URLs were verified against the running stack:

| URL | What it is |
| --- | --- |
| http://localhost/ | React PWA (the product UI) |
| http://localhost/admin/ | Django admin (log in with YOUR email/password from step 6) |
| http://localhost/api/docs/ | Swagger UI for the REST API |
| http://localhost/api/schema/ | Raw OpenAPI schema backing the Swagger page |
| http://localhost/healthz | Liveness probe JSON |
| http://localhost/readyz | Readiness probe JSON incl. database check |

API endpoints live under `http://localhost/api/v1/…` (JWT bearer auth;
register/login via `/api/v1/auth/register` and `/api/v1/auth/login`).

---

## 8. Normal Development Workflow

```bash
git checkout -b feature/my-change

# ...edit code...

docker compose build api worker && docker compose up -d api worker   # backend changes
docker compose build frontend && docker compose up -d frontend       # frontend changes
./scripts/test.sh                                                    # always before committing
```

Key points:

- **Containers serve image-baked code.** After editing backend or frontend
  source, rebuild that service's image and recreate it, otherwise your changes
  are invisible at runtime. This also applies to tests (see §9).
- `docker compose up` is the normal application runtime. Do **not** use
  `python manage.py runserver`; this environment has no host-run workflow.
- Data (database rows, uploads) survives rebuilds and restarts; see §12.

---

## 9. Running Tests

One canonical command:

```bash
./scripts/test.sh
```

Run part of the suite by passing Django test labels:

```bash
./scripts/test.sh                                              # everything
./scripts/test.sh tests.api.test_hardening.RateLimitTests      # one class
./scripts/test.sh tests.unit                                   # one package
```

### Why not `docker compose exec api python manage.py test`?

The `api` container normally runs with `DJANGO_SETTINGS_MODULE=config.settings.prod`.
Running tests that way causes real failures:

- Production throttling is enabled and every test request comes from the same
  IP → one shared rate bucket → ~75 cascading HTTP 429 failures.
- Production Celery is non-eager → enrichment jobs escape to the live Redis
  broker and get consumed by the running worker against the wrong database.
- Argon2 password hashing makes the suite needlessly slow.

The wrapper pins `DJANGO_SETTINGS_MODULE=config.settings.ci` for you — you
never type `-e DJANGO_SETTINGS_MODULE=...` by hand. That test configuration
provides deterministic behavior:

- **PostgreSQL/pgvector** — the suite exercises real migrations, RLS policies
  and vector retrieval inside the `db` container (a throwaway `test_studyai`
  database is created and destroyed per run).
- **Eager Celery** — background jobs execute inline in the test process.
- **Cache/throttle isolation** — throttling off and a dummy cache by default,
  so tests cannot exhaust shared rate buckets.

Explicit throttle tests (`tests/api/test_hardening.py::RateLimitTests`) opt
back into real throttling themselves with tight rates and isolated cache state.

**Production settings remain unchanged.** Nothing about runtime behavior is
weakened; only the test process uses relaxed configuration.

### Built-in safety: the stale-image guard

`scripts/test.sh` compares a hash of every backend source file in your working
tree against the copy baked into the `api` image. If they differ (you edited
code without rebuilding), the script refuses to run and prints the exact
rebuild command — preventing silently wrong results. If you ever see:

```text
ERROR: backend code inside the api image differs from your working tree.
```

run what it tells you, then re-run the script.

---

## 10. Production Configuration Smoke Test

There are TWO different kinds of validation, on purpose:

| Command | Validates | Uses |
| --- | --- | --- |
| `./scripts/test.sh` | Application correctness (116 automated tests) | Deterministic test config (`config.settings.ci`) |
| `./scripts/smoke_prod.sh` | The production configuration itself | The running stack under `config.settings.prod` |

Run the smoke script against your started stack whenever you want proof that
production-like behavior is intact:

```bash
./scripts/smoke_prod.sh
```

It checks (read-only, writes nothing): Django boots under prod settings;
rate limiting ENABLED (auth `30/min`, LocMemCache); Celery NON-eager;
`/healthz` + `/readyz` respond correctly incl. DB roundtrip; the auth throttle
genuinely engages (early 202s, then a real 429); the Celery worker answers
through Redis.

Never run the full test suite against production-like data — that is exactly
what the separation above prevents.

---

## 11. Database and Migrations

PostgreSQL runs in the `db` container. You do not install or run Postgres on
your host, and you do not create databases manually.

**Applying migrations** is automatic: the `api` container runs
`python manage.py migrate` every time it starts. To apply manually:

```bash
docker compose exec api python manage.py migrate
```

**Creating migrations** (only after you change `models.py` somewhere under
`backend/apps/`). Because containers run image-baked code, generate migration
files with a bind-mounted one-off container so the files land in your working
tree (this exact form was verified):

```bash
docker compose run --rm --no-deps -T -v "$PWD/backend:/app" api python manage.py makemigrations
```

Then rebuild/recreate `api` + `worker` (§8) so the new migrations apply, review
the generated files, and commit them. CI enforces that migrations are committed
(`python manage.py makemigrations --check --dry-run` fails the build if you
forgot).

Do not run destructive database commands (flush, `down -v`, SQL deletes) as
part of normal development — see §12 and the referenced reset documentation.

Inspecting state safely:

```bash
docker compose exec api python manage.py showmigrations
docker compose exec api python manage.py shell
```

---

## 12. Stopping and Restarting

```bash
docker compose down       # stop and remove containers — DATA VOLUMES ARE KEPT
docker compose up -d      # start again with existing data
```

Normal `docker compose down` does **not** delete the database or uploaded
files. Volumes (`studyai_pgdata`, etc.) persist until explicitly removed.

Full resets (`docker compose down -v`, volume removal) are intentionally kept
out of the normal workflow. If you truly need one, follow the dedicated
documentation instead:

- `docs/docker-reset-execution.md`
- the "Destructive Commands" / "Full Database Reset" sections of
  `docs/docker-development-environment.md`

---

## 13. Common Problems

### Docker isn't running

Symptom: `Cannot connect to the Docker daemon` / `error during connect`.

Fix: launch **Docker Desktop** and wait until its whale icon stops animating,
then retry. Check with `docker compose version`.

### Port already in use

Symptom on `up`: `Bind for 0.0.0.0:80 failed: port is already allocated`.

Only port 80 is used. Find the owner:

```bash
lsof -iTCP:80 -sTCP:LISTEN        # host process
docker ps                          # other projects' containers publishing :80
```

Stop that process/container, or temporarily map a different host port in
`docker-compose.yml` (e.g. `"8080:80"`) and use http://localhost:8080/.

### Containers are unhealthy

Look at status and then the specific service's logs (real service names):

```bash
docker compose ps
docker compose logs api
docker compose logs db
docker compose logs worker
docker compose logs frontend
```

Typical cases: `db` still initializing a fresh volume (~10 s) while `api` logs
connection errors — wait and let api's retry loop succeed; `frontend` unhealthy
usually means it cannot reach `api` (next item).

### 502 on proxied pages after restarting backend services

nginx resolves `api` by DNS at startup. If `api` was recreated (new container
IP), `frontend` may keep serving 502 for `/`, `/admin/`, `/api/...` while
`docker compose exec api curl localhost:8000/healthz` works fine. Fix:

```bash
docker compose restart frontend
```

### `.env` missing

Symptom: `POSTGRES_PASSWORD: required` or empty-variable errors on any
compose command.

Fix: `cp .env.example .env`, fill in your own generated values (§3).

### Authentication / admin login problems

Passwords are never stored in this repo. Recover your own access:

```bash
docker compose exec api python manage.py createsuperuser     # re-enter same email → offers password reset
docker compose exec api python manage.py changepassword your-email@example.com
```

Browser loops on admin login over http://localhost? Your `.env` likely
re-enabled secure-cookie/HSTS flags — keep them `0` locally (§3), clear site
cookies, `docker compose up -d`.

### Tests unexpectedly return 429

You ran tests directly against the container's default (prod) settings, so all
tests shared one auth rate bucket. Use the wrapper:

```bash
./scripts/test.sh          # pins config.settings.ci automatically
```

See §9 for why this happens.

### Stale Docker image/code

Symptom: `./scripts/test.sh` reports "backend code inside the api image
differs from your working tree", or your runtime changes seem ignored.

This guard exists because containers execute image-baked code. Intended
behavior — rebuild only what changed, exactly as the error message says:

```bash
docker compose build api worker && docker compose up -d api worker
```

Do not blindly nuke images/volumes; the guard exists so you never test stale
code silently.

---

## 14. Project Structure

```text
StudyAI/
├── backend/            # Django project (all API/business logic)
│   ├── config/         # settings modules (base/dev/test/ci/prod), URLs, celery, wsgi
│   ├── apps/           # domain apps: accounts, profiles, subjects, notebooks, canvas,
│   │                   # documents, ingestion, notespace, ai_classroom, retrieval,
│   │                   # questions, tests, chat, revision, references, jobs, evaluation, audit
│   ├── shared/         # cross-cutting utilities: throttles, exceptions, observability/metrics
│   ├── providers/      # swappable provider integrations (LLM chain, OCR, object storage)
│   ├── tests/          # the test suite: api/ unit/ integration/ e2e/
│   └── assets/fonts/   # vendored fonts required inside the api image (PDF rendering)
├── frontend/           # React PWA (Vite + TypeScript), built into the nginx image
├── deploy/             # shared runtime config consumed by compose (deploy/nginx.conf)
├── scripts/            # developer entry points: test.sh, smoke_prod.sh
├── docs/               # development + phase documentation (see §18)
└── StudyAI_app_architecture_v4_1_full.md   # top-level architecture reference (repo root)
```

---

## 15. Development Rules

- Never commit `.env` (it is git-ignored — keep it that way).
- Never put secrets in source code, tests, fixtures, or documentation.
- Never share database passwords, SECRET_KEYs, or tokens through Git or chat;
  every developer generates their own (§3).
- Use your own local admin account (§6); there are no shared accounts.
- Do not modify production settings (`config/settings/prod.py`, base security
  flags, throttle rates, Celery eagerness) merely to make tests pass — tests
  already have their own configuration.
- Use `./scripts/test.sh` for the normal suite and `./scripts/smoke_prod.sh`
  to validate production configuration (§9–10).
- Do not run destructive Docker volume commands (`down -v`, `volume rm`) unless
  you intentionally want to erase local development data (§12).

---

## 16. Git Workflow

Simple feature-branch flow:

```bash
git checkout -b feature/<short-name>

# ...work, rebuild, verify...

./scripts/test.sh                 # full suite must pass

git status                        # review what changed
git diff                          # review how it changed

git add <files>
git commit -m "concise message describing the change"

git push -u origin feature/<short-name>
```

Do not push directly to `main`. Open a pull request from your feature branch —
CI runs automatically on PRs (backend tests on PostgreSQL/pgvector + frontend
build/tests) and must be green before merge.

---

## 17. Quick Start

Copy-paste path from nothing to running stack:

```bash
git clone https://github.com/yashkmr53/StudyAI.git
cd StudyAI
cp .env.example .env
# open .env and paste YOUR OWN generated values for DJANGO_SECRET_KEY and POSTGRES_PASSWORD
#   python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # -> DJANGO_SECRET_KEY
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # -> POSTGRES_PASSWORD

docker compose up -d --build                       # first build takes a few minutes
docker compose ps                                  # wait until api/db/redis/frontend are healthy
docker compose exec api python manage.py createsuperuser   # YOUR email + password
./scripts/test.sh                                  # expect: "Ran 116 tests ... OK"
```

Expected successful outcome:

- `./scripts/test.sh` ends with `OK` (116 tests, 0 failures, 0 errors).
- `./scripts/smoke_prod.sh` ends with `PRODUCTION SMOKE: ALL CHECKS PASSED`.
- http://localhost/ loads the app, http://localhost/admin/ accepts YOUR login,
  http://localhost/readyz returns `{"status":"ok","database":true}`.

---

## 18. Further Documentation

Read in this order once onboarding works end-to-end:

| Document | Contents |
| --- | --- |
| `docs/docker-development-environment.md` | Deep dive on the Docker setup: architecture diagram, env vars, daily commands, destructive-command warnings, troubleshooting |
| `docs/test-baseline-investigation.md` | Why the test configuration looks the way it does: root-cause investigation of historical failures, remediation journal, decisions |
| `docs/docker-reset-execution.md` | Intentional full-reset procedure (destructive) |
| `docs/phase_9_production_readiness/PRODUCTION_READINESS.md` | Production readiness checklist |
| `docs/phase_9_production_readiness/PRODUCTION_RUNBOOK.md` | Operational runbook for deployed environments |
| `docs/phase_9_production_readiness/ARCHITECTURE_TRACEABILITY.md` | Requirement→implementation traceability |
| `StudyAI_app_architecture_v4_1_full.md` | The full application architecture specification (repo root) |
| `.env.example` | Inline comments explaining every environment variable |
