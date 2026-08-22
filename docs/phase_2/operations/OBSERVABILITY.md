# Observability — after Phase 2

Unchanged from Phase 1: request-ID middleware + structured logging are implemented; metrics, health endpoints, tracing, alerts, and error tracking are not. Reference: [`../phase_1/operations/OBSERVABILITY.md`](../../phase_1/operations/OBSERVABILITY.md).

## Phase 2 notes

- Canvas API errors (409 fencing, 422 validation) flow through the standard `django.request` logger with request IDs — correlating a client lock-lost report to server logs works today.
- Client-side signals (pending outbox count, flush failures) are visible only in browser DevTools; no telemetry is shipped.
- Future job metrics (queue depth, retry rate) will attach to the OCR job that Phase 3 introduces via finalize.
