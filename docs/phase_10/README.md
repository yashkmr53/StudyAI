# Phase 10 — Gap Closure Sprint 1

**Date:** 2026-08-23  
**Status:** COMPLETED  
**Source:** `docs/architecture-gap-analysis.md` §6–7

---

## Overview

Phase 10 closes all "implementable immediately (no inputs required)" gaps from the architecture gap analysis. This sprint covers scheduler & backup automation, security hardening, missing backend endpoints, observability metrics, frontend offline hardening, and CI tooling.

---

## Scope

| Category | Gap IDs | Description |
|----------|---------|-------------|
| Scheduler & Backup | C1, C2 | Celery Beat wiring; local backup automation + offsite hook stub |
| Security Hardening | D1–D6 | CORS, CSRF_TRUSTED_ORIGINS, Redis throttle cache, prompt-injection directives, data-minimization filter, CSP header |
| Backend Endpoints | B1, B2, B4, B7, B8, B13 | Notebooks CRUD, document questions, tag rename, enrichment coalescing, token accounting, ProviderError |
| Observability | E | Prometheus metrics endpoint + counters/histograms |
| Frontend Offline | G5–G7 | Online/offline detection, SW Background Sync, outbox state transitions |
| CI/Tooling | H | Coverage measurement, OpenAPI drift check |

**Out of scope (blocked on inputs):** A1–A4, B3, B9, B10, C4, F1, G1–G4

---

## Deliverables

### Sprint 1A — Scheduler + Backup + Security (Week 1)
- Celery Beat scheduler with `reap_stuck_jobs`, `promote_retries`, `daily_backup`, `reset_monthly_budgets`
- `backup_database` / `verify_backup` management commands wired to beat
- `scripts/backup_offsite_hook.sh` stub for offsite copy
- `docs/runbooks/backup_restore.md` runbook with RPO/RTO targets
- CORS (`django-cors-headers`) and `CSRF_TRUSTED_ORIGINS` configuration
- Redis-backed throttle cache (D3) replacing LocMemCache
- Prompt-injection directive in LLM provider calls (D4)
- Data-minimization filter with PII redaction (D5)
- CSP header middleware (D6)

### Sprint 1B — Missing Backend Endpoints (Week 2)
- **Notebooks module** (B1): Full CRUD with RLS (Notebook, NotebookPage, NotebookLine)
- **Document Questions** (B2): `GET /api/v1/documents/{id}/questions`
- **Tag Rename** (B4): `POST /api/v1/tags/{id}/rename/`
- **Enrichment Coalescing** (B7): Coalesce window + change-magnitude threshold
- **Monthly Budget Scaffolding** (B8): Token/cost fields on `ProviderCallLog`, `UserProfile` budget fields, `BudgetService`, `AIBudgetThrottle`
- **ProviderError** (B13): 502 exception class raised on provider failures

### Sprint 1C — Observability + Frontend + CI (Week 3)
- **Prometheus Metrics** (E): `/metrics` endpoint with `ocr_fallback_total`, `schema_validation_failure_total`, `retrieval_latency_seconds`, `evaluation_score`, `product_usage_total`
- **Frontend Online/Offline** (G5): `useOnlineStatus` hook + `OfflineBanner` component
- **Service Worker Background Sync** (G6): Workbox SW with `backgroundSync` for outbox
- **Outbox State Transitions** (G7): `pending → sending → acknowledged / failed → retrying → sending`
- **CI Pipeline**: Coverage gates (backend ≥80%, frontend ≥70%), OpenAPI drift check

---

## Verification Gates

All gates passed:

1. ✅ `docker compose up -d beat` → reaper/retry/backup jobs appear in logs
2. ✅ `python manage.py backup_database --output-dir /tmp/test && python manage.py verify_backup --backup-dir /tmp/test` succeeds
3. ✅ CORS/CSRF headers present on API responses
4. ✅ Redis throttle cache shows keys in DB 2
5. ✅ `ProviderCallLog` contains `input_tokens`, `output_tokens`, `redactions_count`
6. ✅ `ProviderError` raised on mocked 5xx → returns 502 envelope
7. ✅ `/metrics` endpoint exposes Prometheus metrics
8. ✅ Frontend: offline banner shows, SW registers, outbox states transition
9. ✅ CI: coverage ≥80% (backend), ≥70% (frontend); OpenAPI drift check passes

---

## Key Files Reference

| Document | Purpose |
|----------|---------|
| `docs/phase_10/PHASE_10_IMPLEMENTATION_PLAN.md` | Full implementation spec with file paths, verification commands, rollback plan |
| `docs/phase_10/CHECKPOINT.md` | Sprint tracking and progress status |
| `docs/architecture-gap-analysis.md` | Source gap analysis (§6–7) |

---

## Environment Variables Added

See `.env.example` for full list. Key additions:

```bash
# Scheduler
CELERY_BEAT_ENABLED=true

# CORS / CSRF (§23)
CORS_ALLOWED_ORIGINS=https://app.example.com,https://staging.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com,https://staging.example.com

# Redis throttle cache (§23, D3)
REDIS_THROTTLE_URL=redis://redis:6379/2

# Prometheus metrics (§25, E)
PROMETHEUS_METRICS_ENABLED=true

# Enrichment coalescing (§21, B7)
ENRICHMENT_COALESCE_WINDOW_SECONDS=300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15

# Provider input limits (D5 data-minimization)
MAX_PROVIDER_INPUT_CHARS=8000

# Monthly AI budget defaults (B8)
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00
```

---

## Dependencies Added

**Backend (`requirements.txt`):**
- `django-cors-headers>=4.6`
- `django-redis>=5.4`
- `django-prometheus>=2.3`

**Frontend (`package.json`):**
- `vite-plugin-pwa`
- `workbox-background-sync`
- `@vitest/coverage-v8` (dev)

---

## Next Phase (Phase 11)

Blocked on inputs from gap analysis §5:
1. Real OCR provider (A1) — vendor decision + API key
2. Real LLM provider (A2) — vendor + key + model names
3. Neural embedding model (B9) — model choice + backfill plan
4. S3-compatible storage (B10) — bucket/credentials
5. Email service (B3) — SMTP credentials
6. Non-superuser DB role (A3) — DBA approval + migration
7. TLS/domain (C4) — hosting target + cert approach
8. Monitoring (O5) — Sentry/Prometheus endpoint
9. Golden dataset (F1) — 30–50 labeled notes
10. Frontend priority (G1–G4) — product decision on module order

Phase 11 will begin once inputs 1–4 are available.