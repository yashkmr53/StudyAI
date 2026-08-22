# Local Setup — after Phase 7

Delta from Phase 6 ([`../phase_6/setup/LOCAL_SETUP.md`](../setup/LOCAL_SETUP.md)): no new dependencies or services. Migrations add the learning-layer tables.

## Quick path

```bash
brew install pgvector 2>/dev/null; brew services restart postgresql@18
createdb studyai 2>/dev/null || true
./myenv/bin/pip install -r backend/requirements.txt
cd backend && ../myenv/bin/python manage.py migrate && ../myenv/bin/python manage.py runserver
cd ../frontend && npm install && npm run dev
```

## Exercise the learning loop (curl)

```bash
# 0. prerequisites: an OCR-completed document $DID (see phase_3 setup) and a subject
SID=$(create-or-fetch subject id)
curl -X POST .../documents/$DID/revisions ...   # finalize upload → OCR

# 1. assign a subject (tagging anchors to subjects)
psql -d studyai -c "UPDATE documents_document SET subject_id='$SID' WHERE id='$DID';"

# 2. enrich tail generates tags + questions
curl -X POST .../documents/$DID/refresh-ai -H "Authorization: Bearer $TOKEN"

# 3. adaptive test + attempt
TEST=$(curl -s -X POST .../tests -H "$AUTH" -d '{"num_questions":2}')
Q1=$(...); ANS=$(correct index via DB or trial)
curl -X POST .../tests/$TID/attempts -H "$AUTH" -d "{\"question_id\":\"$Q1\",\"selected_index\":$ANS,\"confidence\":0.9}"

# 4. mastery overview + plan
curl .../revision/overview ; curl ".../revision/plans?target_date=YYYY-MM-DD&hours=6"

# 5. chat
curl -X POST .../chat/sessions ; curl -X POST .../chat/sessions/$SID/messages -d '{"content":"…"}'
```

## Tests

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.test ../myenv/bin/python manage.py test tests   # 101 found: 98 pass, 3 skip
cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev  ../myenv/bin/python manage.py test tests --noinput   # 101 pass
cd frontend && npm test && npm run build
```
