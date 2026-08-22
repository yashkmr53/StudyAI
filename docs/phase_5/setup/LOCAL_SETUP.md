# Local Setup — after Phase 5

Delta from Phase 4: **pgvector is now required** for the dense retrieval leg.

## One-time: pgvector

```bash
brew install pgvector
brew services restart postgresql@18
```

The Django migration `retrieval/0000_pgvector_extension` runs `CREATE EXTENSION IF NOT EXISTS vector` automatically on PostgreSQL databases (including fresh test DBs). Verify:

```bash
psql -d studyai -c "SELECT extname FROM pg_extension WHERE extname='vector';"   # vector | 0.8.x
```

## Quick path

```bash
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt     # includes pgvector, fpdf2, celery
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```

## Exercise retrieval (curl)

```bash
# after uploading + finalizing a document (see phase_3 setup doc):
curl -s -X POST http://127.0.0.1:8000/api/v1/search \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"dijkstra"}'
# → results with dense/keyword/rrf scores
```

## Ingest a reference book (optional demo)

```bash
cat > /tmp/book.json <<'JSON'
[{"title":"Graph Theory Reference","author":"E.uler",
  "chapters":[{"number":1,"title":"Shortest paths",
               "text":"Dijkstra finds shortest paths.\n\nBellman-Ford handles negative weights."}]}]
JSON
../myenv/bin/python manage.py ingest_reference_book --file /tmp/book.json
```

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 80 found: 77 pass, 3 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests --noinput   # 80 pass
cd frontend && npm test && npm run build
```
