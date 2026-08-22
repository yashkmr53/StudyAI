# Local Setup — after Phase 2

Same prerequisites and bootstrap as Phase 1 ([`../phase_1/setup/LOCAL_SETUP.md`](../../phase_1/setup/LOCAL_SETUP.md)); nothing new is required to run Phase 2 features.

## Quick path

```bash
brew services start postgresql@18        # if not running
createdb studyai 2>/dev/null || true

./myenv/bin/pip install -r backend/requirements.txt

cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver

cd ../frontend && npm install && npm run dev
```

Open http://localhost:5173 → register → **Canvas** tab:

1. **New sheet** — creates a session (your browser becomes lock holder, generation 1) plus page 1.
2. Draw with mouse/finger — strokes persist to IndexedDB instantly and sync in the background.
3. **+ Page / Finalize page** — pagination and immutable finalize.
4. Open the same sheet from a second tab/device → take over → the first device sees the lock-lost banner.

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 37 found: 35 pass, 2 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests   # 37 pass
cd frontend && npm test && npm run build
```

## Workers

Still not applicable — no Celery tasks exist after Phase 2. Redis not required yet.

Troubleshooting: [../operations/TROUBLESHOOTING.md](../operations/TROUBLESHOOTING.md).
