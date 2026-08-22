# Deployment — after Phase 8

Phase 8 authors the deployment artifacts for the §24/§76 Stage-1 single-VM story. They are **authored but not yet executed on a clean host** — that drill is the remaining pre-production step.

## Artifacts added

| File | Purpose |
|---|---|
| `backend/Dockerfile` | python:3.14-slim; installs requirements + gunicorn; asserts vendored fonts present; runs migrate + gunicorn |
| `docker-compose.yml` | db (pgvector/pgvector:pg16) · redis · api (migrate+gunicorn) · worker (celery) · frontend (nginx serving PWA + /api proxy) |
| `deploy/nginx.conf` | SPA static + /api proxy + client_max_body_size aligned with upload cap |

## Production env checklist

See [`ENVIRONMENT_AND_SECRETS.md`](ENVIRONMENT_AND_SECRETS.md): non-superuser DB role, real secret key, allowed hosts, HTTPS termination, `RATE_LIMITING_ENABLED=True`, budgets set.

## Remaining pre-production drills

1. `docker compose up` on a clean VM; register/login/enrich smoke through nginx.
2. Scheduled backups (`backup_database` via cron + offsite copy of objectstore dir).
3. Load re-test at target scale ([../../scripts/load_test.py](../../scripts/load_test.py)).
