# Observability — after Phase 5

Infrastructure unchanged: request-ID middleware + structured logging; no metrics/health/tracing/alerts. Reference: [`../phase_4/operations/OBSERVABILITY.md`](../../phase_4/operations/OBSERVABILITY.md).

Phase 5 additions to the log stream:

- Index completion INFO lines: `kept/staled/created/embedded` counters per document — the incremental behavior is directly observable.
- Reference ingestion INFO lines from the management command.
- Retryable job failures log full tracebacks (introduced late Phase 4, used heavily here).

Still absent: retrieval latency measurement, queue-depth/retry-rate aggregates, health endpoints.
