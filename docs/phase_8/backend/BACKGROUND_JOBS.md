# Background Jobs — after Phase 8 (final)

Registry unchanged from Phase 7: `ocr` · `pdf_render` · `index` · `enrich`. Runtime unchanged: durable rows, atomic claim, EMA backoff, dead-letter, reaper function, eager/broker/executor dispatch.

Phase 8 additions are **observational and protective**, not new jobs:

- `/api/v1/status` (staff) exposes queue depth, dead-letter count, retryable backlog, 24 h created/retried.
- ProviderCallLog records every LLM chain attempt (latency/success/error).
- Budget gate can 429 enrich/chat before a job is even enqueued when the profile's daily AI budget is exhausted.

Full registry and state machine: [`../phase_7/backend/BACKGROUND_JOBS.md`](../../phase_7/backend/BACKGROUND_JOBS.md).

Still open: beat schedule for the reaper; real-broker integration run; metrics export beyond the status endpoint.
