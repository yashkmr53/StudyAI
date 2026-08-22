# Local Setup — after Phase 6

Delta from Phase 5 ([`../phase_5/setup/LOCAL_SETUP.md`](../../phase_5/setup/LOCAL_SETUP.md)): `jsonschema` dependency added (in requirements.txt). No new services.

## Quick path

```bash
brew install pgvector 2>/dev/null; brew services restart postgresql@18
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```

## Exercise enrichment (curl)

```bash
# after a document is uploaded and OCR-completed (see phase_3 setup):
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/$DID/enrich \
  -H "Authorization: Bearer $TOKEN"          # → 202 {job}
sleep 1
curl -s http://127.0.0.1:8000/api/v1/documents/$DID/enrichment \
  -H "Authorization: Bearer $TOKEN"          # blocks + citations + ai_stale flag
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/$DID/refresh-ai \
  -H "Authorization: Bearer $TOKEN"          # forced regeneration, 202
```

With a READY reference book ingested (`manage.py ingest_reference_book`), the pipeline also produces reference-grounded gap_fill blocks.

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 89 found: 86 pass, 3 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests --noinput   # 89 pass
cd frontend && npm test && npm run build
```
