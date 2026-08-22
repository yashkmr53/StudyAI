# Background Jobs

## Current reality

The durable `Job` model and its state machine are implemented and tested, but **no jobs are defined, enqueued, or executed anywhere in the system yet.** Celery is configured (`config/celery.py`) with a broker URL pointing at Redis — which is not installed. There are no workers, no beat schedule, no reaper.

## Job registry

| Job name | Queue | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure | Dead-letter | Monitoring |
|---|---|---|---|---|---|---|---|---|---|---|
| *(none implemented)* | — | — | — | — | — | — | — | — | — | — |

Planned producers (Phases 3–7): OCR per page/revision, chunking+embedding, enrichment, question generation, PDF rendering.

## Implemented model (`apps/jobs/models.py`)

Fields: `id (uuid)`, `job_type`, `resource_type`, `resource_id`, `profile_id (uuid, nullable)`, `revision_id (uuid, nullable)`, `idempotency_key (unique)`, `status`, `attempt_count`, `last_error`, `started_at`, `finished_at`, `created_at`.

Indexes: `(status, created_at)`, `(job_type, resource_type, resource_id)`.

### State transitions

```text
QUEUED
  ↓ claim()  — atomic: UPDATE … WHERE status='queued' (single winner; attempt_count++)
RUNNING
  ├──► SUCCEEDED            via mark_succeeded()   [sets finished_at]
  ├──► FAILED_RETRYABLE     via mark_retryable(err) [records last_error]
  │        └── re-queue → QUEUED   (backoff policy NOT yet implemented)
  ├──► FAILED_DEAD_LETTER   via dead_letter(err)    [sets finished_at]
  └──► CANCELLING ──► CANCELLED   (transitions modeled; no cancel API/task yet)
```

Tested semantics (`tests/unit/test_shared.py::JobModelTests`): first claim wins, second claim returns False, attempt_count = 1.

## Idempotency keys (formats implemented, unused by any job)

```text
ocr:{page_id}:{content_hash}:{pipeline_version}
embedding:{chunk_id}:{content_hash}:{embedding_model_version}
enrichment:{revision_id}:{prompt_version}:{model}
question_generation:{revision_id}:{prompt_version}
```

Source: `shared/idempotency/keys.py`; mirrored client-side in `frontend/src/utils/idempotency.ts`. The DB unique constraint on `jobs_job.idempotency_key` is the duplicate-write backstop.

## Worker contract (to implement in Phase 3)

```text
load trusted job payload → BEGIN → SET LOCAL app.current_profile_id = job.profile_id
→ work → COMMIT / ROLLBACK      # never accept client-supplied profile IDs
```

Helper already available: `shared/database/rls.py::profile_scoped_transaction`.

## Not yet implemented

- Task definitions and queue routing (Celery or DB-polling executor).
- Retry policy with exponential backoff + jitter.
- Per-job-type timeouts and the stuck-RUNNING reaper (beat task).
- Cancellation API (`POST /api/v1/jobs/{id}/cancel`) and status endpoint.
- Job monitoring/observability surfaces.
