# Docker Reset — Execution Journal

Date: 2026-08-22 (UTC). Operator: agent + user. Scope: StudyAI Compose project only.

Secrets policy for this journal: no passwords, secret keys, tokens, or credential
values appear below. Where relevant they are recorded as `[REDACTED]` /
"manually configured by user".

---

## 1. Repository Audit

Command: `git status --short`, file inspection (`docker-compose.yml`, `.env*`,
`.gitignore`, `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/nginx.conf`,
`backend/config/settings/*`, `backend/config/urls.py`, `backend/apps/accounts/*`,
CI workflow).

Purpose: understand intended architecture before touching anything.

Result:
- Compose project with services `db`, `redis`, `api`, `worker`, `frontend`.
- Settings module in Docker: `config.settings.prod`; DB config env-driven.
- nginx proxied `/api/`, `/healthz`, `/readyz` but **not** `/admin/` (admin URL fell through to the SPA fallback — verified live).
- No static-file serving story under gunicorn+DEBUG=False (no whitenoise, no `STATIC_ROOT`).
- `prod.py` bugs found: whitespace-split of comma-separated `DJANGO_ALLOWED_HOSTS`; hard-coded secure-cookie/HSTS flags incompatible with plain-HTTP localhost.
- Repo had zero commits; host `myenv/` virtualenv and `studyai_backup.sql` dumps present but out of scope.

Files changed: none (audit only).
Containers/volumes changed: none.

## 2. Docker Environment Audit

Commands: `docker ps -a`, `docker compose ps`, `docker volume ls`,
`docker network ls`, `docker images`, `docker inspect <studyai-container>`.

Result (pre-reset state):
- StudyAI containers running 13 h: `studyai-{api,worker,frontend,db,redis}-1`; api not published to host; restart policy `no`.
- Volumes: `studyai_pgdata`, `studyai_objectstore`. Network: `studyai_default`.
- Unrelated project present (`backend-*` containers, `backend_postgres-data`,
  `backend_redis-data`, `care` network) — explicitly excluded from all operations.
- Live probe: `http://localhost/admin/` returned the React SPA shell (false-positive 200), confirming the missing admin route.
- Existing `.env` contained prior `DJANGO_SECRET_KEY` / `POSTGRES_PASSWORD`
  (values inspected by presence only, never printed).

## 3. Configuration Fixes (non-destructive)

Files changed:
- `backend/config/settings/prod.py` — comma-split `ALLOWED_HOSTS`;
  env-driven `DEBUG`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, `DJANGO_HSTS_SECONDS` (defaults remain production-safe);
  added `STATIC_ROOT`; wired `OBJECT_STORAGE_*` / TTL from environment.
- `deploy/nginx.conf` — added `/admin/` proxy block and `/static/` alias.
- `docker-compose.yml` — shared `django_static` volume (api rw → frontend ro),
  `collectstatic` added to api startup command before migrate, env passthrough
  for new knobs, healthchecks (redis/api/frontend), `restart: unless-stopped`,
  YAML anchor shared by api/worker environments.
- `backend/.dockerignore`, `frontend/.dockerignore` — created (host uploads,
  caches and node_modules were being copied into build context previously).
- `.env` — rebuilt to target variable structure; existing `DJANGO_SECRET_KEY`
  and `POSTGRES_PASSWORD` preserved verbatim at that point (values never displayed).
- Validation: `docker compose config --services` → db, redis, api, frontend,
  worker; full `docker compose config` parsed cleanly (output redacted before display).

Errors: none during validation.

## 4. Manual Secret Checkpoint

User paused the workflow, generated fresh credentials themselves (Option B), and
confirmed: "Secrets configured — continue."

Recorded facts only:
- `POSTGRES_PASSWORD`: manually configured by user
- `DJANGO_SECRET_KEY`: manually configured by user
- Admin email chosen: `admin@studyai.dev`
- Django admin password: manually configured by user (never entered chat)

## 5. Destructive Reset (user-approved)

Command (2026-08-22T13:28:12Z): `docker compose down --remove-orphans`
Command (2026-08-22T13:28:28Z): `docker volume rm studyai_pgdata studyai_objectstore && docker rmi studyai-api studyai-worker studyai-frontend`

Removed:
- Containers: studyai-api-1, studyai-worker-1, studyai-frontend-1, studyai-db-1, studyai-redis-1
- Volumes: studyai_pgdata (PostgreSQL data), studyai_objectstore (uploads)
- Images: studyai-api, studyai-worker, studyai-frontend
- Network: studyai_default

Not touched: `backend-*` containers/volumes/images, `care` network, base images
(pgvector/pgvector:pg16, redis:7-alpine). No `docker system prune` used.

Verification post-reset: no studyai containers, volumes, or networks remained;
unrelated containers still listed untouched.

## 6. Rebuild & Start

Command (13:28:35Z): `docker compose build` → images built (frontend cached layers reused from earlier same-day build).
Command (13:28:50Z): `docker compose up -d`.

Created: network `studyai_default`; volumes `studyai_django_static` (new),
`studyai_pgdata`, `studyai_objectstore` (recreated empty).
Started: db → healthy; redis → healthy; worker; api; frontend.

Assumption: fresh Postgres initialized its role/database from `.env` values on first boot.

## 7. Database Initialization & Verification

- api startup ran `collectstatic` + `migrate --noinput` then gunicorn (per compose command); api healthcheck → healthy.
- `showmigrations`: **60 applied, 0 unapplied**.
- Worker log: connected to `redis://redis:6379/0`, `celery@… ready`.
- Celery ping from api container: `pong`.
- `GET /readyz` through nginx: `{"status":"ok","database":true}`.

Errors: none.

## 8. Superuser Creation (manual checkpoint)

Agent handed the exact command to the user and STOPPED:

```bash
docker compose exec api python manage.py createsuperuser
```

User ran it interactively (email `admin@studyai.dev`; password entered privately)
and confirmed: "Superuser created — continue."

Post-confirmation verification via `manage.py shell` (no password accessed):
`email=admin@studyai.dev, is_active=True, is_staff=True, is_superuser=True`.

## 9. API Authentication Verification

All requests through nginx at http://localhost. Test account created via
register endpoint; password/tokens generated inside the test shell and never printed.

| Endpoint | Result |
| --- | --- |
| POST `/api/v1/auth/register` | 201, user created |
| POST `/api/v1/auth/login` | 200, access+refresh issued |
| GET `/api/v1/profiles` with Bearer token | 200 |
| POST `/api/v1/auth/refresh` | 200, refresh rotated |
| reuse of old refresh after rotation | 401 (blacklist works) |
| POST `/api/v1/auth/logout` | 204 |
| POST `/api/v1/auth/password-reset` | 202 |

Notes/errors encountered while testing:
- First attempt showed refresh→401/logout→422: caused by the test script reusing a
  rotated refresh token twice. Not an app bug; correct blacklist behavior. Re-run clean.
- Authenticated call still succeeds right after logout: expected — logout
  blacklists the *refresh* token only (see `LogoutView`); access tokens expire on TTL.

## 10. Routing / URL Verification

Content-checked (not just status codes):

| URL | Result |
| --- | --- |
| http://localhost/ | SPA served (`<title>StudyAI</title>`) |
| http://localhost/admin/login/ | Real Django admin login page (`action="/admin/login/"`) |
| /static/admin/css/base.css | 200 via nginx static volume (24.5 KB) |
| http://localhost/api/docs/ | Swagger UI rendered; `/api/schema/` → 200 |
| http://localhost/healthz | `{"status":"ok"}` |
| http://localhost/readyz | `{"status":"ok","database":true}` |
| /api/v1/status unauthenticated | 401 (staff-only enforced) |

Django remains unpublished to the host (no port 8000 mapping) — verified via `docker ps`.

## 11. Persistence Verification

Command (13:35:52Z): `docker compose restart` → all five services back up;
db/redis/api healthy; readyz OK.

Survived restart (verified):
- superuser flags still true; registered verify-users still present (row durability)
- migrations 60 applied / 0 unapplied
- Celery ping → pong
- `/admin/login/` → 200

`down -v` intentionally NOT run after initialization.

## 13. Post-Restart Healthcheck Fix

After `docker compose restart`, `frontend` reported unhealthy although it served
traffic correctly. Diagnosis: busybox wget resolves `localhost` to `::1` only and
does not fall back to IPv4, while nginx listens on IPv4 `0.0.0.0:80`.

Fix: frontend healthcheck retargeted to `http://127.0.0.1/healthz` in
`docker-compose.yml`; container recreated via `docker compose up -d frontend`;
all services then reported healthy.

## 12. Documentation

Created this journal plus `docs/docker-development-environment.md` (architecture,
services table, env var reference, credentials policy, command reference,
destructive-command warnings, reset procedure, troubleshooting, docker-only rule).
`.env.example` updated to mirror the final variable set with placeholder-only values.

## Final File Inventory

Modified: `backend/config/settings/prod.py`, `deploy/nginx.conf`,
`docker-compose.yml`, `.env.example`, `.env` (local only, git-ignored).
Created: `docs/docker-development-environment.md`, `docs/docker-reset-execution.md`,
`backend/.dockerignore`, `frontend/.dockerignore`.
Deleted: none.
