# Background Jobs — after Phase 2

**Unchanged from Phase 1: the durable `Job` model and its state machine are implemented and tested, but no jobs are defined, enqueued, or executed.** Celery remains configured with no tasks; Redis is not installed.

See [`../phase_1/backend/BACKGROUND_JOBS.md`](../../phase_1/backend/BACKGROUND_JOBS.md) for the full model documentation, state machine, and idempotency key formats.

## Phase 2 relationship to jobs

- The finalize flow (`CanvasSyncService.finalize_page`) is the designated producer of the first real job (OCR). Its transaction contains a marked extension point; the job creation lands in Phase 3 together with the ingestion models.
- Canvas autosave deliberately never triggers OCR/LLM work (§4) — only finalize will, in Phase 3.
- Stroke sync is fully synchronous HTTP; it does not use the job system.

## Job registry

| Job name | Queue | Trigger | Status |
|---|---|---|---|
| *(none — first candidate: `ocr` from page finalize, Phase 3)* | — | — | ❌ |
