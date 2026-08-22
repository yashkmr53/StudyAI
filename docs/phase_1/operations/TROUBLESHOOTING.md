# Troubleshooting

Practical guide for failures possible **today**. Items marked *(future)* describe diagnostics for components that don't exist yet.

## PostgreSQL connection failure

- **Symptom:** `django.db.utils.OperationalError: connection to server … No such file or directory`
- **Likely cause:** Postgres not running (dev connects via socket `/tmp`).
- **Diagnose:** `pg_isready`
- **Fix:** `brew services start postgresql@18`

## Database does not exist

- **Symptom:** `FATAL: database "studyai" does not exist`
- **Fix:** `createdb studyai && cd backend && ../myenv/bin/python manage.py migrate`

## Migration failure

- **Symptom:** errors during `migrate` referencing a relation/policy that exists.
- **Diagnose:** `../myenv/bin/python manage.py showmigrations`; `psql -d studyai -c "\d+ profiles_profile"`.
- **Fix:** for local resets: `dropdb studyai && createdb studyai && migrate`. RLS policy conflicts: drop via `DROP POLICY IF EXISTS …` before re-running `subjects/0002_enable_rls`.

## "RLS doesn't work"

- **Symptom:** queries return other profiles' rows despite policies.
- **Likely cause:** connected as superuser (`yash`) — PostgreSQL exempts superusers from RLS by design.
- **Diagnose:** `psql -d studyai -c "SELECT rolsuper FROM pg_roles WHERE rolname=current_user;"` → expect `t` in dev.
- **Fix:** none locally (accepted, documented). Production must use a non-superuser role; verify with `SET app.current_profile_id` absent → zero rows.

## ModuleNotFoundError: django

- **Cause:** system Python used instead of the central env.
- **Fix:** always `./myenv/bin/python backend/manage.py …` or `cd backend && ../myenv/bin/python manage.py …`. Missing deps: `./myenv/bin/pip install -r backend/requirements.txt`.

## Tests run 0 tests

- **Cause:** missing `__init__.py` in a test package dir.
- **Fix:** add it (all dirs under `backend/tests/` need one).

## Backend unreachable from frontend

- **Symptom:** browser requests to `/api/*` fail (`ECONNREFUSED`) or 404.
- **Diagnose:** is Django up on `127.0.0.1:8000`? Vite proxy config in `frontend/vite.config.ts`.
- **Fix:** start backend first.

## 401 loop after idle

- **Cause:** access token expired (30 min) and refresh failed — e.g., another tab already rotated the refresh token, blacklisting this tab's copy.
- **Fix:** sign in again. Client retries refresh exactly once by design.

## Redirected to /login after registering

- **Diagnose:** DevTools → Network: was `/auth/register` 201? Is `localStorage.studyai.access` set?
- **Fix:** clear site data and retry; check backend log line for the request ID shown in the error envelope.

## Port already in use

```bash
lsof -ti :8000 | xargs kill    # backend
lsof -ti :5173 | xargs kill    # frontend
```

## Stale PWA assets

- **Symptom:** old UI after dependency/config change.
- **Fix:** DevTools → Application → Service Workers → Unregister, then hard reload.

## Redis unavailable / worker not processing / OCR failure / LLM failure / embedding failure / PDF generation failure / session lock loss / offline sync conflict / object storage failure

*(future)* — None of these components are implemented yet (no workers, no OCR/LLM/embedding providers, no PDF renderer, no canvas fencing, no storage-serving routes). When they land, each gets symptom → diagnose → fix entries here.
