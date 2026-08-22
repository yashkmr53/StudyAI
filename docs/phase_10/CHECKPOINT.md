# Phase 10 Checkpoint — Gap Closure Sprint 1

**Created:** 2026-08-23  
**Status:** PLANNED — Ready for implementation  
**Source:** `docs/architecture-gap-analysis.md` §6–7

---

## What This Phase Covers

All **"implementable immediately (no inputs required)"** items from the gap analysis:

- **C1** Celery Beat scheduler (reaper, retry promotion, daily backup)
- **C2** Local backup automation + offsite hook stub
- **D1–D6** Security hardening (CORS, CSRF, Redis throttle, prompt-injection directives, data-minimization filter, CSP)
- **B1** Notebooks module (CRUD + RLS)
- **B2** `GET /api/v1/documents/{id}/questions` endpoint
- **B4** Tag rename REST endpoint
- **B7** Enrichment coalescing window + change-magnitude threshold
- **B8** Token columns + monthly budget scaffolding
- **B13** `ProviderError` (502) exception class
- **E** Observability metrics (Prometheus counters/histograms + middleware)
- **G5–G7** Frontend offline hardening (online detection, SW Background Sync, outbox state transitions)
- **H** CI tooling (coverage measurement, OpenAPI drift check)

---

## Execution Order (3 Sprints)

| Sprint | Focus | Est. Duration |
|--------|-------|---------------|
| 1A | Scheduler + Backup + Security | Week 1 |
| 1B | Missing Backend Endpoints/Models | Week 2 |
| 1C | Observability + Frontend Offline + CI | Week 3 |

---

## Key Files to Reference

| Document | Purpose |
|----------|---------|
| `docs/phase_10/PHASE_10_IMPLEMENTATION_PLAN.md` | Full implementation spec with file paths, verification commands, rollback plan |
| `docs/architecture-gap-analysis.md` | Source gap analysis (sections 6–7) |

---

## Environment Variables Required (add to `.env.example`)

```
CELERY_BEAT_ENABLED=true
CORS_ALLOWED_ORIGINS=https://app.example.com,https://staging.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com,https://staging.example.com
REDIS_THROTTLE_URL=redis://redis:6379/2
PROMETHEUS_METRICS_ENABLED=true
ENRICHMENT_COALESCE_WINDOW_SECONDS=300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15
MAX_PROVIDER_INPUT_CHARS=8000
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00
```

---

## Dependencies to Install

**Backend (`requirements/base.txt`):**
- `django-cors-headers`
- `django-redis`
- `django-prometheus`

**Frontend (`package.json`):**
- `vite-plugin-pwa`
- `workbox-background-sync`
- `@vitest/coverage-v8` (dev)

---

## Verification Gates (Must Pass Before Phase 11)

1. `docker compose up -d beat` → reaper/retry/backup jobs appear in logs
2. `python manage.py backup_database --output-dir /tmp/test && python manage.py verify_backup --backup-dir /tmp/test` succeeds
3. CORS/CSRF headers present on API responses
4. Redis throttle cache shows keys in DB 2
5. `ProviderCallLog` contains `input_tokens`, `output_tokens`, `redactions_count`
6. `ProviderError` raised on mocked 5xx → returns 502 envelope
7. `/metrics` endpoint exposes Prometheus metrics
8. Frontend: offline banner shows, SW registers, outbox states transition
9. CI: coverage ≥80% (backend), ≥70% (frontend); OpenAPI drift check passes

---

## Out of Scope (Blocked on Inputs)

| Item | Blocked On |
|------|------------|
| A1 Real OCR provider | Vendor choice + API key |
| A2 Real LLM provider | Vendor + key + model names |
| A3 RLS under deployment role | DBA approval for non-superuser role |
| A4 Backup offsite/RPO-RTO | Hosting target + offsite destination |
| B3 Password reset completion | Email service credentials |
| B9 Neural embeddings | Model decision + backfill plan |
| B10 S3 storage | Bucket + credentials |
| C4 TLS termination | Domain + cert approach |
| F1 Golden dataset | 30–50 human-labeled notes |
| G1–G4 Frontend modules | Product priority decision |

---

## Next Steps

1. **Start Sprint 1A** — Begin with `backend/config/celery.py` beat_schedule and `docker-compose.yml` beat service
2. **Parallelize** — Security config (D1, D2, D6) and Redis throttle (D3) can run in parallel
3. **Track progress** — Update this checkpoint with completion status per task
4. **Phase 11 planning** — Begin gathering input decisions (vendor choices, hosting, golden data) during Sprint 1C