# Troubleshooting — after Phase 5

Prior guides: [`../phase_4/operations/TROUBLESHOOTING.md`](../operations/TROUBLESHOOTING.md) (uploads, OCR, PDF, locks) and earlier. New entries:

## `type "vector" does not exist` during migrate/tests

- **Cause:** pgvector extension missing on that database (fresh test DBs get it via migration `retrieval/0000`; the main dev DB needs it too).
- **Fix:**
  ```bash
  brew install pgvector
  brew services restart postgresql@18
  psql -d studyai -c 'CREATE EXTENSION IF NOT EXISTS vector;'
  ```

## Search returns zero results

Checklist:
1. Did OCR complete? (`page.ocr_status == completed`)
2. Was indexing run? The index job fires automatically after OCR/edit; verify `NoteChunk.objects.filter(document_id=…)` has rows with `stale=false`.
3. Query tokens must appear in content for the keyword leg; dense leg needs PostgreSQL.
4. Reference chunks require their book `status = ready`.

## `InconsistentMigrationHistory` on retrieval app

- **Cause:** a migration was added *before* an already-applied one (ordering dependency).
- **Fix (dev):** drop the app's tables + history and re-migrate:
  ```sql
  DROP TABLE IF EXISTS retrieval_notechunk CASCADE;
  DELETE FROM django_migrations WHERE app='retrieval';
  ```
  then `manage.py migrate retrieval`.

## Embeddings look "wrong"/identical

The hashing embedder is lexical — paraphrases won't match strongly. This is expected until the model swap (F-001). Verify determinism instead of semantics in tests.

## Search 401/422

401 → no bearer token. 422 → empty query or a subject UUID that doesn't belong to the caller.

## Redis unavailable / enrichment failure

*(future)* — no broker or LLM stages exist yet.
