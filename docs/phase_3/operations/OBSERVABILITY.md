# Observability — after Phase 3

Unchanged infrastructure: request-ID middleware + structured logging; no metrics/health/tracing/alerts. Reference: [`../phase_1/operations/OBSERVABILITY.md`](../../phase_1/operations/OBSERVABILITY.md).

Phase 3 additions to the log stream:

- `apps.documents.services` INFO line on OCR completion: job id, attempted provider chain, line count, review flag.
- Job state warnings: dead-letter events logged with attempt counts; broker-unavailable dispatch falls back with a WARNING while the job stays QUEUED.

These make single-job diagnosis possible today via `/api/v1/jobs/{id}` + grep by request/job id. Aggregate observability (queue depth, retry rate, dead-letter count — spec §25) remains ❌ pending Phase 8.
