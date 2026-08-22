# Environment and Secrets

Configuration is environment-driven. `config/settings/base.py` loads `<repo>/.env` via python-dotenv. Template: `.env.example` at repo root (placeholders only).

## Variables

| Variable | Required? | Purpose | Example format | Used by | How to obtain | Rotation |
|---|---|---|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Yes (shell) | Selects settings module | `config.settings.dev` \| `test` \| `prod` | manage.py, wsgi | — | n/a |
| `DJANGO_DEBUG` | Dev only | Enables DEBUG | `1` / `0` | dev, prod | — | n/a |
| `DJANGO_SECRET_KEY` | **Prod (required)** | Signing: JWTs?, sessions, signed storage URLs | 64+ char random string | prod settings; `LocalObjectStorage._sign` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` | Rotate → invalidates all tokens & signed URLs; plan maintenance window |
| `DJANGO_ALLOWED_HOSTS` | Prod (required) | Host header allowlist | `studyai.example.com` | prod settings | your DNS | n/a |
| `POSTGRES_DB` | Prod | Database name | `studyai` | prod DATABASES | DBA / hosting console | n/a |
| `POSTGRES_USER` | Prod | DB role (**non-superuser** for RLS) | `studyai_app` | prod DATABASES | DBA | Rotate via `ALTER ROLE … PASSWORD` |
| `POSTGRES_PASSWORD` | Prod | DB password | random | prod DATABASES | secret manager | same as above |
| `POSTGRES_HOST` | Prod | DB host | `db.internal` | prod DATABASES | infra | n/a |
| `POSTGRES_PORT` | No | DB port | `5432` | prod DATABASES | infra | n/a |
| `POSTGRES_SSLMODE` | No | TLS mode | `require` | prod DATABASES | infra policy | n/a |
| `CELERY_BROKER_URL` | Phase 3+ | Redis broker DSN | `redis://localhost:6379/0` | `config/celery.py` | infra | rotate with Redis auth |
| `OBJECT_STORAGE_BACKEND` | No | Storage provider selector | `local` (only value today) | `providers/registry.py` | — | n/a |
| `OBJECT_STORAGE_LOCAL_DIR` | No | Local storage root | `var/objectstore` | base settings | — | n/a |
| `SIGNED_URL_TTL_SECONDS` | No | Signed URL lifetime | `300` | `LocalObjectStorage` | security policy | n/a |
| `OCR_API_KEY` / `LLM_API_KEY` / `EMBEDDING_MODEL_PATH` | Not yet | Future provider credentials | placeholder | reserved | provider consoles | per provider |

Dev-only note: `base.py` carries a hardcoded fallback `SECRET_KEY` explicitly marked insecure; `prod.py` requires the env var and has no fallback.

## Critical security rules

1. **Never commit** real passwords, API keys, tokens, private keys, cloud creds, or DB passwords.
2. `.gitignore` excludes `.env`, `backend/var/`, virtualenvs, build output.
3. Logs must never contain passwords, tokens, signed URLs, or raw note content.
4. A repository-wide secret scan was performed before publishing these docs (`rg` for key-like assignments) — no secrets found outside the marked dev-only fallback.

## Settings matrix

| Module | DB | Purpose |
|---|---|---|
| `config.settings.dev` | PostgreSQL `studyai` @ `/tmp` socket, user `yash` | local dev + RLS integration tests |
| `config.settings.test` | SQLite `:memory:` | fast hermetic unit tests |
| `config.settings.prod` | env-driven PostgreSQL, `sslmode=require` | deployment |
