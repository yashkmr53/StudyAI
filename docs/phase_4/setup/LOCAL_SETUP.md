# Local Setup — after Phase 4

Same bootstrap as Phase 3 ([`../phase_3/setup/LOCAL_SETUP.md`](../setup/LOCAL_SETUP.md)). New in Phase 4: `fpdf2` dependency (already in requirements.txt) and vendored fonts under `backend/assets/fonts/` — no extra setup steps.

## Quick path

```bash
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```

## Exercise NoteSpace end-to-end (UI)

1. http://localhost:5173 → register/sign in.
2. **NoteSpace** tab → choose a PNG/JPEG → upload runs OCR automatically (mock provider, eager execution).
3. **Edit transcription** — fix lines, flag headings, save (creates revision 2).
4. **Generate PDF** → poll completes → **Download PDF** opens the signed URL.

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 67 found: 65 pass, 2 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests   # 67 pass
cd frontend && npm test && npm run build
```
