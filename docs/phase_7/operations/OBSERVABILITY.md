# Observability — after Phase 7

Infrastructure unchanged: request-ID middleware + structured logging; no metrics/health/tracing/alerts. Reference: [`../phase_1/operations/OBSERVABILITY.md`](../../phase_1/operations/OBSERVABILITY.md).

Phase 7 additions:

- Tagging INFO lines (tag counts per document).
- Question-generation INFO lines (new question count per document).
- Chat answered INFO line with citation count and verdict (`apps.chat.services`).

Still absent: latency histograms, queue-depth aggregates, health endpoints, alerting — Phase 8.
