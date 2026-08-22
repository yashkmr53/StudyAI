# Background Jobs — after Phase 3

Phase 1 introduced the durable Job model; **Phase 3 wires it to real work**. PostgreSQL remains the source of truth; Redis is optional (dev/test run eager; a DB-polling executor exists).

## Runtime components

| Component | Location | Role |
|---|---|---|
| Idempotent creation | `apps/jobs/services.py::get_or_create_job` | unique idempotency_key; races resolved |
| Dispatch | `dispatch_job` | Celery task via broker, or inline when `CELERY_TASK_ALWAYS_EAGER` (dev/test); broker failure leaves job QUEUED |
| Claim | `Job.claim()` | atomic conditional UPDATE queued→running (single winner) |
| Execution | `run_claimed_job` | handler dispatch + RLS context + state transitions |
| Retry/backoff | `retry_backoff` + `next_retry_at` | 5s·2^attempts capped 300s + jitter; executor promotes due FAILED_RETRYABLE |
| Dead-letter | after `JOBS_MAX_ATTEMPTS=3` | terminal, retains last_error |
| Reaper | `reap_stuck_jobs` (600 s timeout) | RUNNING → FAILED_RETRYABLE requeue |
| Executor command | `manage.py process_jobs [--loop] [--reap]` | §24 DB-polling alternative — no broker needed |

## Registered jobs

| Job name | Trigger | Input | Output | Retry | Timeout | Idempotency | Failure behavior | Status |
|---|---|---|---|---|---|---|---|---|
| `ocr` | finalize-upload / canvas page finalize / retry-processing | resource_id = DocumentPageRevision id | DocumentLine* + revision/page status (`completed`/`needs_review`) | 3 attempts, exponential+jitter | 600 s (reaper) | `ocr:{page}:{hash}:{pipeline}` unique; completed revisions short-circuit | retryable → dead-letter; source data untouched (§28) | ✅ implemented (mock providers 🔧) |

## State machine (as exercised)

```text
QUEUED --claim()--> RUNNING --ok--> SUCCEEDED
                        |--error & attempts<3--> FAILED_RETRYABLE --due--> QUEUED
                        |--error & attempts>=3--> FAILED_DEAD_LETTER
QUEUED --cancel--> CANCELLED      RUNNING --cancel--> CANCELLING --> CANCELLED (cooperative)
```

## Monitoring

Job health is queryable (`/api/v1/jobs/{id}`) but no aggregate metrics/alerting exist yet. OCR completion logs at INFO with provider + line count.

## Not yet done

Beat schedule for the reaper (task defined, nothing schedules it); real-broker integration test; queue-depth/retry-rate metrics.
