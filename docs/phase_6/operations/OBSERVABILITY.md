# Observability — after Phase 6

Infrastructure unchanged: request-ID middleware + structured logging; no metrics/health/tracing/alerts. Reference: [`../phase_1/operations/OBSERVABILITY.md`](../../phase_1/operations/OBSERVABILITY.md).

Phase 6 additions:

- Enrichment completion INFO line: document id, block count, verified count (`apps.ai_classroom.services`).
- Retryable job failures log full tracebacks (from Phase 5) — enrichment stage errors are directly diagnosable from logs.
- EvalRun rows provide point-in-time quality snapshots once datasets exist.

Still absent: retrieval/enrichment latency histograms, queue-depth aggregates, health endpoints, alerting.
