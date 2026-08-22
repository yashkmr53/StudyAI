# Architecture — Phase 10

**Status:** Extended with gap-closure components

---

## Overview

Phase 10 adds no new architectural layers. It closes implementation gaps in existing components per architecture v4.1 (§1–80). All additions follow established patterns.

---

## Component Additions

### Scheduler Layer (C1)
```
┌─────────────────────────────────────────────────────────────┐
│                     Celery Beat                             │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ reap-stuck-  │ │ promote-     │ │ daily-backup       │  │
│  │ jobs (5m)    │ │ retries (2m) │ │ (02:30 UTC)        │  │
│  └──────────────┘ └──────────────┘ └────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ reset-monthly-budgets (1st of month)                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Redis Broker (DB 0)                      │
└─────────────────────────────────────────────────────────────┘
```

### Backup Automation (C2, A4)
```
daily_backup task (beat)
    │
    ├─► pg_dump → /backups/{db}_{timestamp}.dump
    │
    └─► backup_offsite_hook.sh --source-dir /backups --dest-uri $OFFSITE_BACKUP_URI
            │
            ├─► S3: aws s3 sync
            ├─► GCS: gsutil rsync
            └─► rsync: rsync -avz
```

### Security Hardening (D1–D6)

| Component | Location | Architecture Ref |
|-----------|----------|------------------|
| CORS Middleware | `CorsMiddleware` before `CommonMiddleware` | §23 |
| CSRF Trusted Origins | `CSRF_TRUSTED_ORIGINS` setting | §23 |
| Redis Throttle Cache | `CACHES['throttle']` → `django-redis` | §23, D3 |
| Prompt-Injection Directive | `LLMChainProvider.generate_structured()` | §72, D4 |
| Data-Minimization Filter | `_sanitize_for_provider()` in chain | §73, D5 |
| CSP Header | `SecurityHeadersMiddleware` | §23, D6 |

### Observability (E)
```
┌─────────────────────────────────────────────────────────────┐
│                  Prometheus Metrics                         │
│  /metrics endpoint (django-prometheus)                      │
│  ┌──────────────┐ ┌──────────────────────┐ ┌─────────────┐  │
│  │ Counters     │ │ Histograms           │ │ Gauges      │  │
│  │ ocr_fallback │ │ retrieval_latency    │ │ evaluation  │  │
│  │ schema_val   │ │                      │ │ _score      │  │
│  │ product_usage│ │                      │ │             │  │
│  └──────────────┘ └──────────────────────┘ └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Frontend Offline (G5–G7)
```
┌─────────────────────────────────────────────────────────────┐
│                    Browser Runtime                          │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ useOnline    │ │ Offline      │ │ Service Worker     │  │
│  │ Status Hook  │ │ Banner       │ │ (sw.js)            │  │
│  │              │ │              │ │ - backgroundSync   │  │
│  │ online/      │ │ Shows when   │ │ - cache-first      │  │
│  │ offline events│ │ offline      │ │ - network-first    │  │
│  └──────────────┘ └──────────────┘ │   API              │  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Outbox (IndexedDB)                                 │  │
│  │ pending → sending → acknowledged                   │  │
│  │              └──→ failed → retrying → sending      │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Changes

### Enrichment Coalescing (B7)
```
User Edit → enqueue_enrichment()
    │
    ├─► Check existing non-stale EnrichedNote → return if exists
    │
    ├─► Check pending job within coalesce_window
    │       │
    │       ├─► Compute change magnitude
    │       │       │
    │       │       ├─► ≤ threshold → return existing job (coalesced)
    │       │       │
    │       │       └─► > threshold → create new job
    │       │
    │       └─► No pending job → create new job
    │
    └─► Job created with coalesced_from → previous job
```

### Monthly Budget Enforcement (B8)
```
AI Request (enrich/chat)
    │
    ├─► AIBudgetThrottle.allow_request()
    │       │
    │       ├─► Standard rate limit (Redis throttle cache)
    │       │
    │       └─► BudgetService.check_and_increment(user, tokens, cost)
    │               │
    │               ├─► Reset if budget_reset_date passed
    │               │
    │               ├─► Check token budget → 429 if exceeded
    │               │
    │               ├─► Check cost budget → 429 if exceeded
    │               │
    │               └─► Atomic increment counters
    │
    └─► ProviderCallLog populated with token counts
```

---

## Deployment Changes

### Docker Compose
- New `beat` service (reuses `worker` image, command: `celery -A config beat -l INFO`)
- Mounts: `objectstore` volume for backup access

### Environment Variables
All new vars documented in `.env.example` and `CHANGELOG.md`

### Health Checks
- Beat service depends on `db` (healthy) and `redis` (started)
- `/metrics` endpoint added for Prometheus scraping

---

## Rollback Procedures

See `docs/phase_10/PHASE_10_IMPLEMENTATION_PLAN.md` → Rollback Plan table

| Component | Rollback |
|-----------|----------|
| Beat scheduler | `docker compose stop beat && docker compose rm -f beat` |
| Redis throttle | Revert `CACHES['throttle']` to `LocMemCache` |
| CORS/CSRF | Remove `django-cors-headers`, delete env vars |
| CSP | Remove `CSPMiddleware` from middleware stack |
| Notebooks | `python manage.py migrate notebooks zero && rm -rf apps/notebooks` |
| Budget fields | Migration rollback (data loss) or keep nullable |
| ProviderError | Remove from exceptions, revert provider raise logic |
| Prometheus | Remove `django-prometheus`, delete metrics files |
| Frontend SW | Delete `public/sw.js`, remove PWA plugin |
| CI steps | Revert `.github/workflows/ci.yml` |

---

## Related Documentation

- `docs/phase_10/PHASE_10_IMPLEMENTATION_PLAN.md` — Full implementation spec
- `docs/architecture-gap-analysis.md` — Source gap analysis
- `docs/phase_6/architecture/ARCHITECTURE.md` — Base architecture