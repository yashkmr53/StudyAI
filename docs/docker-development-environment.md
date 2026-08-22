# StudyAI Docker Development Environment

Beginner-friendly guide to the one and only way this project runs locally: **Docker Compose**.
There is no host `runserver` workflow anymore. If a service isn't running, you start Docker, not Python.

---

## Docker-Only Rule

```text
Do not use python manage.py runserver for this environment.
```

Every Django command runs inside the `api` container:

```bash
docker compose exec api python manage.py <command>
```

The host machine needs exactly two things installed: **Docker Desktop** and **git**.
No `myenv/`, no local Postgres, no local Redis.

---

## Architecture

```text
Browser
   |
   v
frontend (nginx :80)  <-- the ONLY service published to your machine
   |---- /api/   ----> api (Django/gunicorn :8000)
   |---- /admin/ ----> api (Django admin)
   |---- /static/ --> files collected by Django at startup
   |---- /healthz ---> api liveness probe
   |---- /readyz  ---> api readiness (checks PostgreSQL)
   |---- anything else -> React SPA (index.html fallback)
        api ----> db    (PostgreSQL 16 + pgvector)   volume: studyai_pgdata
        api ----> redis (Celery broker)
      worker ----> redis (consumes tasks)
      worker ----> db
   api + worker share studyai_objectstore (uploaded files) and
   studyai_django_static (admin CSS/JS written by api, served by nginx).
```

- Only port **80** is exposed to the host. Django's 8000, Postgres' 5432 and Redis' 6379 are internal to the Docker network.
- All services sit on the `studyai_default` network and reach each other by name (`db`, `redis`, `api`).

## Services

| Service  | Purpose                        | Internal Port | Host Port |
| -------- | ------------------------------ | ------------: | --------: |
| frontend | React PWA bundle + nginx proxy |            80 |        80 |
| api      | Django via gunicorn            |          8000 |  internal |
| worker   | Celery worker                  |             — |         — |
| db       | PostgreSQL 16 + pgvector       |          5432 |  internal |
| redis    | Redis 7 (broker only)          |          6379 |  internal |

Settings module used everywhere in Docker: `config.settings.prod`
with development-safe overrides supplied through `.env` (see below).

## Environment Variables

All live in `.env` at the repo root (git-ignored, never committed).

| Variable | Purpose |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | Which settings file Django loads inside containers (`config.settings.prod`). |
| `DJANGO_DEBUG` | `0` keeps debug pages off even in development (gunicorn-safe). |
| `DJANGO_SECRET_KEY` | Signs sessions/CSRF/signed URLs. **Manually configured by user.** Not a login password. |
| `DJANGO_ALLOWED_HOSTS` | Hostnames Django answers for. Comma-separated (`localhost,127.0.0.1`). |
| `DJANGO_SECURE_SSL_REDIRECT` | `0` locally because nginx terminates plain HTTP. Defaults to `1`. |
| `DJANGO_SESSION_COOKIE_SECURE` | `0` locally so session cookies work over HTTP on localhost. Defaults to `1`. |
| `DJANGO_CSRF_COOKIE_SECURE` | Same idea for the CSRF cookie. Defaults to `1`. |
| `DJANGO_HSTS_SECONDS` | HSTS cache time. `0` locally (would otherwise pin localhost to HTTPS). Defaults to `31536000`. |
| `POSTGRES_DB` / `POSTGRES_USER` | Database and role created when the `db` volume is first initialized. |
| `POSTGRES_PASSWORD` | Password for that role. **Manually configured by user.** |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Always `db:5432` from inside the Docker network. |
| `POSTGRES_SSLMODE` | `disable` — traffic never leaves the private Docker network. |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` — where worker/api enqueue tasks. |
| `OBJECT_STORAGE_BACKEND` | `local` stores uploads on the shared `objectstore` volume (S3 later). |
| `OBJECT_STORAGE_LOCAL_DIR` | Upload root inside containers (`var/objectstore` → `/app/var/objectstore`). |
| `SIGNED_URL_TTL_SECONDS` | Lifetime of private-file download links. |

Security note: the production-safe defaults in `backend/config/settings/prod.py`
(SSL redirect, secure cookies, HSTS) are switched off **only** by `.env` so that
plain-HTTP localhost works. Never ship those `=0` values beyond your machine.

## Credentials

```text
PostgreSQL database:     studyai
PostgreSQL user:         studyai
PostgreSQL password:     manually configured by user

Django admin email:      admin@studyai.dev
Django admin password:   manually configured by user (never stored in this repo)

Django SECRET_KEY:       manually configured by user, lives only in .env
                         used for cryptographic signing, NOT a login password
```

The PostgreSQL password (machine-to-machine auth between Django and Postgres)
and the Django admin password (you logging into the browser) are unrelated credentials.

## Daily Commands

Start / stop / inspect:

```bash
docker compose up -d          # start everything (first time adds --build)
docker compose down           # stop and remove containers (data volumes kept)
docker compose ps             # status + health of each service
docker compose logs -f        # follow all logs
docker compose logs -f api    # just Django
docker compose logs -f db     # just PostgreSQL
docker compose restart        # bounce services (keeps data)
docker compose build          # rebuild images after code changes
```

Django management (always through Docker):

```bash
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
docker compose exec api python manage.py shell
docker compose exec api python manage.py showmigrations
```

After editing backend code: `docker compose build && docker compose up -d`.
After editing frontend code: same (the image rebuilds the SPA bundle).

## Destructive Commands (read carefully)

| Command | Effect |
| --- | --- |
| `docker compose down -v` | **Deletes ALL data** — database rows, users, uploads. Only for an intentional full reset. |
| `docker volume rm studyai_pgdata` | Deletes just the PostgreSQL data. |
| `docker volume rm studyai_objectstore` | Deletes uploaded documents/images. |
| `docker system prune -a` | Nukes unused images across ALL projects on your machine. **Never run this here.** |

## Full Database Reset (intentional wipe)

⚠️ This deletes every row, user, and upload. There is no undo.

```bash
docker compose down --remove-orphans
docker volume rm studyai_pgdata studyai_objectstore
docker compose up -d --build
# wait ~30s for api healthcheck to pass (it re-runs migrations automatically)
docker compose exec api python manage.py createsuperuser
```

Migrations rerun automatically on `api` startup; the superuser must be recreated.

## URLs

| URL | What |
| --- | --- |
| http://localhost/ | React frontend |
| http://localhost/admin/ | Django admin (session login) |
| http://localhost/api/docs/ | Swagger UI (OpenAPI schema at `/api/schema/`) |
| http://localhost/healthz | Liveness JSON |
| http://localhost/readyz | Readiness JSON incl. DB check |

API auth endpoints: `/api/v1/auth/register`, `/login`, `/logout`, `/refresh`,
`/password-reset` (JWT bearer tokens; logout revokes the refresh token,
access tokens simply expire after their lifetime).

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `no configuration file provided` or empty-variable errors on any `docker compose` command | `.env` missing or missing keys. Recreate from `.env.example`; supply real values yourself. |
| `POSTGRES_PASSWORD: required` during `up` | Same cause — compose refuses to start without secrets. |
| `db` unhealthy / api logs show connection refused | `db` still initializing its fresh volume (~10 s). Check `docker compose logs db`, then restart `api`. |
| `DisallowedHost` | Your hostname is not in `DJANGO_ALLOWED_HOSTS` (comma-separated, e.g. add `myhost.local`). Restart api afterwards. |
| Redis/Celery errors in worker log | `docker compose logs redis`; confirm `CELERY_BROKER_URL=redis://redis:6379/0`. Worker auto-reconnects. |
| `/admin/` shows the React app instead of login page | nginx config not loaded: ensure `deploy/nginx.conf` has the `/admin/` block, then `docker compose restart frontend`. |
| `/admin/` unstyled (raw HTML, no CSS) | Static volume issue: check api startup ran `collectstatic` (`docker compose logs api`), then `docker compose restart frontend`. |
| Admin login loops back / CSRF error over http://localhost | Cookie/HSTS flags were re-enabled. In `.env`: `DJANGO_SECURE_SSL_REDIRECT=0`, `DJANGO_SESSION_COOKIE_SECURE=0`, `DJANGO_CSRF_COOKIE_SECURE=0`, `DJANGO_HSTS_SECONDS=0`, then clear site cookies and `docker compose up -d`. Browser may also have cached HSTS from earlier experiments — try incognito once. |
| Port 80 already in use | Another process owns port 80 (often an old container). Find it: `lsof -iTCP:80 -sTCP:LISTEN` or `docker ps` for other projects; stop that, or change the mapping in `docker-compose.yml` to `"8080:80"`. |
| Migration errors | Read `docker compose logs api`. For a broken half-migrated dev DB use the Full Database Reset above. |
| `401` after logging out of the API | Expected: logout blacklists the refresh token; the access token stays valid until expiry (30 min). |

## First-Time Setup Summary (fresh machine)

```bash
cp .env.example .env      # then fill in YOUR OWN generated values (see .env.example comments)
docker compose up -d --build
# wait for `docker compose ps` to show api healthy (migrations run automatically)
docker compose exec api python manage.py createsuperuser
open http://localhost/admin/
```
