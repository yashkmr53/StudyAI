# Observability

## Implemented

### Request IDs
`shared/observability/request_id.py`
- `RequestIDMiddleware` assigns `req_<uuid-hex>` per request (honors incoming `X-Request-ID`).
- Propagated to: response header `X-Request-ID`, every log line via `RequestIDLogFilter`, and the §61 error envelope (`error.request_id`).
- One ID correlates a client report ↔ response ↔ all log lines for that request.

### Structured logging
`LOGGING` in `config/settings/base.py`:

```text
{levelname} {asctime} {name} request_id={request_id} {message}
```

Console handler, root level INFO. Django's `django.request` logger emits ERROR lines with request IDs on 4xx/5xx (visible in dev server output).

### Sensitive-data rule
No passwords, tokens, signed URLs, or raw note content are logged — enforced by convention; nothing in the codebase logs request bodies.

## Not implemented

| Capability | Status | Notes |
|---|---|---|
| Health endpoints (`/healthz`, `/readyz`) | ❌ | Needed before any deployment |
| Metrics (job health, queue depth, retry rate, dead-letter count, OCR fallback rate, provider usage, LLM latency, schema-validation failures, retrieval latency, citation status distribution) | ❌ | Spec §25 list; most depend on Phase 3+ features |
| Tracing (spans/OTel) | ❌ | Request-ID correlation only |
| Error tracking service (Sentry etc.) | ❌ | None configured |
| Alerts | ❌ | None |
| Internal status page | ❌ | Planned v1 item |
| Performance monitoring (p95 API/retrieval targets §75) | ❌ | No measurement harness |

## Where logs live today

Dev server stdout only. No file shipping, no aggregation. Acceptable for single-developer local work; insufficient for staging/production.
