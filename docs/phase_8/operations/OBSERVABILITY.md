# Observability — after Phase 8

Implemented now:

- **Health endpoints**: /healthz (liveness), /readyz (DB probe) — [../backend/API.md](../backend/API.md).
- **Internal status page** `/api/v1/status` (staff): job health by status/type, queue depth, dead-letter count, retryable backlog, 24 h created/retried, provider usage from ProviderCallLog, citation verification distribution, request p50/p95/p99 from the in-process latency registry.
- **Request timing**: TimingMiddleware attaches X-Duration-Ms and records into the histogram.
- **Provider telemetry**: ProviderCallLog rows per LLM chain attempt.
- **Structured logs** with request IDs remain the primary debug surface.

Still absent: external APM/alerting, metrics export formats (Prometheus), log shipping. These need infrastructure decisions (§76 Stage 4+) and are tracked in KNOWN_LIMITATIONS.md.
