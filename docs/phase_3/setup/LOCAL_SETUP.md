# Local Setup — after Phase 3

Same bootstrap as Phase 2 ([`../phase_2/setup/LOCAL_SETUP.md`](../setup/LOCAL_SETUP.md)); nothing new is required. New in Phase 3: an optional broker-free worker command.

## Quick path

```bash
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt   # now includes celery
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```

Dev settings run jobs **eagerly** (inline), so uploads process without Redis. For realistic async behavior:

```bash
cd backend && ../myenv/bin/python manage.py process_jobs --reap        # one pass
../myenv/bin/python manage.py process_jobs --loop --reap --interval 2  # worker mode
```

## Exercise the upload flow (curl)

```bash
B=http://127.0.0.1:8000/api/v1
# 1. login → TOKEN; 2. profile id → PID
DOC=$(curl -s -X POST $B/documents -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"profile\":\"$PID\",\"source_type\":\"image\",\"filename\":\"n.png\"}")
URL=$(echo "$DOC" | python3 -c "import json,sys;print(json.load(sys.stdin)['upload']['url'])")
DID=$(echo "$DOC" | python3 -c "import json,sys;print(json.load(sys.stdin)['document']['id'])")
PGID=$(echo "$DOC" | python3 -c "import json,sys;print(json.load(sys.stdin)['page']['id'])")

printf '\x89PNG\r\n\x1a\nfake' > /tmp/n.png
curl -s -X PUT "http://127.0.0.1:8000$URL" -H 'Content-Type: image/png' --data-binary @/tmp/n.png

curl -s -X POST $B/documents/$DID/revisions -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"page_id\":\"$PGID\"}"     # 202 + job
```

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 60 found: 58 pass, 2 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests   # 60 pass
cd frontend && npm test && npm run build
```
