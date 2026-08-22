# Troubleshooting — after Phase 6

Prior guides: [`../phase_5/operations/TROUBLESHOOTING.md`](../operations/TROUBLESHOOTING.md) and earlier. New entries:

## Enrichment returns 422 "no completed revisions"

The document has pages but none reached `completed`/`needs_review` OCR status. Finalize uploads or wait for the index job; platform reference documents cannot be enriched by design.

## GET /enrichment returns 404

No enrichment exists yet for this document (or it belongs to another user). POST `/enrich` first.

## Enrich job FAILED_RETRYABLE / DEAD_LETTER

- **Diagnose:** `last_error` on `/api/v1/jobs/{id}`. Typical causes: schema validation failure of a stage output, or unexpected evidence shape.
- **Fix:** `POST /documents/{id}/refresh-ai` re-enqueues with a fresh key. If a broken provider output is the cause, fix/rollback the provider and refresh again.

## Overview block shows "unsupported"

Working as designed: rules-v1 verifier scores lexical support between block content and cited chunks; the overview's meta-text is not backed by chunk text. It remains visible with its honest verdict — do not "fix" by editing verdicts manually.

## gap_fill blocks absent

Gap detection only reports topics present in READY reference chunks but missing from user notes. Ingest a reference book (`manage.py ingest_reference_book`) covering the subject, then refresh-ai.

## ai_stale stays true after edits

Staleness clears only by regenerating: run refresh-ai. The flag is informational until automatic re-enrichment scheduling lands (§21 coalescing — Phase 8).
