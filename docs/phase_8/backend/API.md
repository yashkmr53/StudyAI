# API Reference — after Phase 8

Base `/api/v1` · Bearer auth (health endpoints + signed storage URLs open).
Authoritative contract: [`../openapi.yaml`](../openapi.yaml).

Phase 1–7 endpoints unchanged — see prior phase API docs. New in Phase 8:

---

## GET /healthz — public
Liveness. `200 {"status": "ok"}` always (unless process dead).

## GET /readyz — public
Readiness with DB roundtrip.
`200 {"status":"ok","database":true}` · `503 {"status":"degraded","database":false}`.

## GET /api/v1/status — staff only (§25 internal status page)

```json
{
  "jobs": {
    "by_status": {"queued": 0, "running": 0, "succeeded": 12, …},
    "by_type_status": {"ocr:succeeded": 9, "index:succeeded": 9, "enrich:succeeded": 2},
    "queue_depth": 0,
    "dead_letter_count": 0,
    "retryable_count": 0,
    "created_last_24h": 12,
    "retried_last_24h": 0
  },
  "providers": { "usage": {"mock:ok": 14}, "ocr_fallback_rate": null },
  "citations": { "verification_distribution": {"supported": 4, "unsupported": 2} },
  "requests": { "total": 184, "p50_ms": 44.1, "p95_ms": 131.7, "p99_ms": 163.2 },
  "counters": { "requests.GET./api/v1/documents": 42 },
  "database": { "vendor": "postgresql" }
}
```

Errors: `403` for non-staff.

## GET /api/v1/audit?action={filter} — staff only (§23)

Paginated audit entries: `{id, actor_email, action, resource_type, resource_id, metadata, ip_address, created_at}`.

Events currently recorded: `user.registered`, `user.login`, `user.logout`, `document.created`. Errors: `403` non-staff.

## Rate limiting behavior (§23/§61)

| Scope | Applies to | Rate |
|---|---|---|
| `auth` | login/register/logout/refresh/password-reset | 30/min |
| `ai` | search / enrich / chat messages | 120/min |

Exceeded → `429 RATE_LIMITED` envelope with `Retry-After` header. Gated by `RATE_LIMITING_ENABLED` (true in prod; false in dev/test unless a test enables it).

## Not implemented

Notebooks endpoint group; documents tags listing is present; questions generation standalone endpoint remains internal to enrich/refresh-ai.
