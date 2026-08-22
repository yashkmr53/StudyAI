# Deployment

Reality check: **only Development exists.** Staging and Production are designed (settings + checklist) but have no infrastructure, images, or pipelines.

## Development (exists)

| Component | Reality |
|---|---|
| Web/app server | Django dev server (`manage.py runserver`) on `127.0.0.1:8000` |
| Frontend | Vite dev server on `:5173`, proxying `/api` → `127.0.0.1:8000` |
| Database | Local PostgreSQL 18 (`studyai`), socket auth |
| Workers | None (no tasks exist) |
| Object storage | Local filesystem `backend/var/objectstore/` |
| HTTPS | None (localhost) |

## Staging

**Does not exist.** No environment, data, or config.

## Production (planned — nothing deployed)

Target topology per spec §24/§76 Stage 1:

```text
Single VM + Docker Compose
  ├── nginx (TLS termination)  → gunicorn (Django)
  ├── PostgreSQL 18 (+pgvector later)
  ├── Redis (broker only)
  ├── Celery worker(s) + beat
  └── static assets (collectstatic / frontend dist)
```

### Already implemented for production

`config/settings/prod.py`:
- Requires `DJANGO_SECRET_KEY` from env (no fallback), explicit `ALLOWED_HOSTS`.
- HSTS 1 year (includeSubdomains, preload), SSL redirect, secure session/CSRF cookies.
- `SECURE_PROXY_SSL_HEADER` for reverse proxy; DB via env with `sslmode=require`.

### Required before first production deploy

1. Non-superuser DB role (RLS enforcement depends on it).
2. Dockerfile(s) + compose file — **not written yet**.
3. Gunicorn/nginx configs — **not written yet**.
4. Rate limiting (DRF throttles or proxy-level).
5. CORS allowlist or same-origin serving of the PWA.
6. Health endpoints (`/healthz`, `/readyz`) — **not implemented**.
7. Migrations run as release step: `manage.py migrate --no-input`.
8. Static: `manage.py collectstatic`; frontend `npm run build` → serve `dist/` same-origin.
9. Backups per [../operations/BACKUP_AND_RECOVERY.md](../operations/BACKUP_AND_RECOVERY.md) (currently nonexistent).

### Migrations & rollback (planned procedure)

```text
Deploy = build image → run migrations → switch traffic.
Rollback = previous image tag; migrations are forward-only today
(no reverse-tested down migrations beyond Django's built-ins).
```

### Monitoring

None configured. See [../operations/OBSERVABILITY.md](../operations/OBSERVABILITY.md).
