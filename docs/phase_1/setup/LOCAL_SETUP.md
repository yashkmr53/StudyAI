# Local Setup

From clean checkout to running system. Every command below is verified against this repository.

## Prerequisites

| Tool | Version used | Verify |
|---|---|---|
| Python | 3.14 via `myenv/` (already in repo) | `./myenv/bin/python --version` |
| Node.js | ≥ 20 (24 used) | `node --version` |
| PostgreSQL | 18 (Homebrew) | `pg_isready` |
| Redis | **not required yet** | — |

## 1. Start PostgreSQL and create the database

```bash
brew services start postgresql@18        # skip if already running
pg_isready                               # expect: accepting connections
createdb studyai 2>/dev/null || true     # idempotent
```

## 2. Backend dependencies (central env)

```bash
./myenv/bin/pip install -r backend/requirements.txt
```

## 3. Environment (optional in dev)

Defaults work out of the box (`config/settings/dev.py`). To override:

```bash
cp .env.example .env    # then edit values
```

## 4. Migrate

```bash
cd backend
../myenv/bin/python manage.py migrate
```

Applies all migrations including `subjects/0002_enable_rls.py` (RLS policies). Verify:

```bash
psql -d studyai -c "SELECT tablename, policyname FROM pg_policies WHERE schemaname='public';"
# → profiles_profile / subjects_subject policies
```

## 5. Run the backend

```bash
../myenv/bin/python manage.py runserver       # http://127.0.0.1:8000
```

Optional admin user (`/admin/`):

```bash
../myenv/bin/python manage.py createsuperuser --email admin@example.com
```

## 6. Run the frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 — proxies /api → 127.0.0.1:8000
```

Register an account at http://localhost:5173/register; you land in the app shell with a default profile.

## 7. Workers

**Not applicable yet** — no Celery tasks exist (Phase 1 has no async work). Redis is not installed. See [../backend/BACKGROUND_JOBS.md](../backend/BACKGROUND_JOBS.md).

## 8. Seed data

None. There is no seed/fixtures command; data is created through the API or admin.

## 9. Tests

```bash
# backend, fast (SQLite; RLS tests skip)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests

# backend, full (PostgreSQL; RLS tests execute)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev ../myenv/bin/python manage.py test tests

# frontend
cd frontend && npm test && npm run build
```

## 10. Smoke check

```bash
curl -s http://127.0.0.1:8000/api/schema/ -o /dev/null -w '%{http_code}\n'   # 200
TOKEN=$(curl -s -X POST http://localhost:5173/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"smoke@test.dev","password":"s3curePass!x"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['access'])")
curl -s http://localhost:5173/api/v1/profiles -H "Authorization: Bearer $TOKEN"
```

Troubleshooting: [../operations/TROUBLESHOOTING.md](../operations/TROUBLESHOOTING.md).
