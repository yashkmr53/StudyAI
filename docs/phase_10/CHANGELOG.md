# Phase 10 Changelog

**Date:** 2026-08-23  
**Phase:** Gap Closure Sprint 1  
**Status:** COMPLETED

---

## Summary

Closed all "implementable immediately" gaps from architecture-gap-analysis.md §6–7 across three sprints.

---

## Sprint 1A — Scheduler + Backup + Security (2026-08-23)

### Added
- **Celery Beat Scheduler** (`backend/config/celery.py`): `beat_schedule` with four periodic tasks:
  - `reap-stuck-jobs` — every 5 min
  - `promote-retries` — every 2 min
  - `daily-backup` — 02:30 UTC daily
  - `reset-monthly-budgets` — 1st of month 00:00 UTC
- **Beat Service** (`docker-compose.yml`): New `beat` service using worker image
- **Backup Offsite Hook** (`scripts/backup_offsite_hook.sh`): Stub implementation with documented integration points for S3/GCS/rsync
- **Backup Runbook** (`docs/runbooks/backup_restore.md`): RPO 24h / RTO 4h targets, manual/automated procedures, quarterly drill schedule

### Security Hardening
- **CORS** (`django-cors-headers`): `CORS_ALLOWED_ORIGINS` env-driven, `CorsMiddleware` before `CommonMiddleware`
- **CSRF**: `CSRF_TRUSTED_ORIGINS` env-driven
- **Redis Throttle Cache**: `CACHES['throttle']` using `django-redis` on DB 2
- **Prompt-Injection Directive** (`backend/providers/llm/chain.py`): Prepended to all LLM calls
- **Data-Minimization Filter**: Truncation to `MAX_PROVIDER_INPUT_CHARS` + PII redaction (email, phone, credit card, SSN) with `redactions_count` logged
- **CSP Header** (`SecurityHeadersMiddleware`): Full policy with `default-src 'self'`, `connect-src 'self' ws: wss:`

### Modified
- `backend/config/settings/base.py`: All new env vars, CORS/CSRF/Redis/Prometheus settings
- `backend/config/urls.py`: Added `apps.notebooks.urls`, `apps.ai_classroom.urls`, `/metrics` endpoint
- `backend/requirements.txt`: Added `django-cors-headers`, `django-redis`, `django-prometheus`
- `backend/apps/audit/tasks.py`: `daily_backup` task invokes offsite hook
- `backend/apps/audit/models.py`: `ProviderCallLog` already had token fields from earlier phase

---

## Sprint 1B — Missing Backend Endpoints (2026-08-23)

### B1: Notebooks Module
- **Models** (`backend/apps/notebooks/models.py`): `Notebook`, `NotebookPage`, `NotebookLine` mirroring Document layer
- **Views** (`backend/apps/notebooks/views.py`): `NotebookViewSet`, `NotebookPageViewSet` with full CRUD
- **Serializers** (`backend/apps/notebooks/serializers.py`): Create/Update/List serializers
- **URLs** (`backend/apps/notebooks/urls.py`): Nested routes under `/api/v1/notebooks/<uuid>/pages/...`
- **Admin** (`backend/apps/notebooks/admin.py`): Full admin registration
- **Tests** (`backend/apps/notebooks/tests/test_notebooks.py`): 17 tests covering CRUD + RLS
- **Migrations**: `0001_initial.py`, `0002_enable_rls.py` (4 RLS policies)

### B2: Document Questions Endpoint
- **View** (`backend/apps/questions/views.py`): `DocumentQuestionsViewSet` with owner-scoped queryset
- **Serializer** (`backend/apps/questions/serializers.py`): `QuestionSerializer` with `answer_text`
- **URL** (`backend/apps/documents/urls.py`): `GET /documents/<uuid:document_id>/questions`
- **Tests** (`backend/apps/questions/tests/test_document_questions.py`): 4 tests

### B4: Tag Rename Endpoint
- **View** (`backend/apps/ai_classroom/views.py`): `TagViewSet.rename` action
- **Serializer** (`backend/apps/ai_classroom/serializers.py`): `TagSerializer`, `TagChangeLogSerializer`
- **URLs** (`backend/apps/ai_classroom/urls.py`): Router registration
- **Tests** (`backend/apps/ai_classroom/tests/test_tag_rename.py`): 6 tests

### B7: Enrichment Coalescing
- **Service** (`backend/apps/ai_classroom/services.py`): `_compute_change_magnitude()`, coalescing logic in `enqueue_enrichment()`
- **Job Model** (`backend/apps/jobs/models.py`): Added `coalesced_from` FK for traceability
- **Settings**: `ENRICHMENT_COALESCE_WINDOW_SECONDS`, `ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD`

### B8: Monthly Budget Scaffolding
- **Profile Model** (`backend/apps/accounts/models.py`): `monthly_token_budget`, `monthly_cost_budget_usd`, `current_month_token_usage`, `current_month_cost_usd`, `budget_reset_date`
- **BudgetService** (`backend/apps/accounts/services/budget.py`): `check_and_increment()`, `get_remaining()`, monthly reset logic
- **AIBudgetThrottle** (`backend/shared/throttles.py`): Integrates budget check into `ai` throttle scope
- **Views Updated**: `DocumentViewSet.enrich`, `refresh_ai`, `ChatSessionViewSet.messages` use `AIBudgetThrottle`

### B13: ProviderError Exception
- **Exception** (`backend/shared/exceptions/handlers.py`): `ProviderError` (502, `PROVIDER_ERROR`)
- **Providers** (`backend/providers/llm/chain.py`, `backend/providers/ocr/chain.py`): Raise `ProviderError` on non-retryable failures

---

## Sprint 1C — Observability + Frontend + CI (2026-08-23)

### E: Prometheus Metrics
- **Metrics Module** (`backend/shared/observability/metrics.py`): Prometheus counters/histograms + in-process fallback
- **Metrics View** (`backend/shared/observability/views.py`): `MetricsView` at `/metrics`
- **Metrics Exposed**:
  - `ocr_fallback_total` (counter, labels: provider, reason)
  - `schema_validation_failure_total` (counter, labels: endpoint, field)
  - `retrieval_latency_seconds` (histogram, labels: query_type)
  - `evaluation_score` (gauge, labels: metric, dataset)
  - `product_usage_total` (counter, labels: feature, action)
- **Helper Functions**: `ocr_fallback_inc()`, `schema_validation_failure_inc()`, `retrieval_latency_observe()`, `evaluation_score_set()`, `product_usage_inc()`

### G5: Frontend Online/Offline Detection
- **Hook** (`frontend/src/hooks/useOnlineStatus.ts`): `navigator.onLine` + `online`/`offline` events
- **Component** (`frontend/src/components/OfflineBanner.tsx`): Fixed banner with connection status
- **Integration** (`frontend/src/app/App.tsx`): Banner rendered at root

### G6: Service Worker Background Sync
- **SW** (`frontend/public/sw.js`): Workbox-based with `backgroundSync` for outbox, cache-first static assets
- **Registration** (`frontend/src/main.tsx`): SW registration on load
- **Vite Config** (`frontend/vite.config.ts`): `vite-plugin-pwa` with `workbox.backgroundSync`

### G7: Outbox State Transitions
- **Outbox Service** (`frontend/src/services/sync/outbox.ts`): `pending → sending → acknowledged / failed → retrying → sending`
- **IndexedDB** (`frontend/src/db/indexeddb/db.ts`): `updateOperationStatus()`, `getOperationsByStatus()`
- **Store** (`frontend/src/state/useOutboxStore.ts`): Zustand store with `refresh()`, `flush()`, `retry()`

### H: CI Tooling
- **Workflow** (`.github/workflows/ci.yml`): Backend (pytest + coverage ≥80%), Frontend (vitest + coverage ≥70%), Docker compose build, OpenAPI drift check
- **OpenAPI Snapshot** (`docs/openapi/schema.yml`): Committed reference schema
- **Backend Coverage Config** (`backend/pyproject.toml`): `branch = true`, `fail-under=80`
- **Frontend Coverage**: `@vitest/coverage-v8` with `npm run coverage`

---

## Files Created/Modified Summary

### Backend (New)
```
backend/apps/notebooks/models.py
backend/apps/notebooks/views.py
backend/apps/notebooks/serializers.py
backend/apps/notebooks/urls.py
backend/apps/notebooks/admin.py
backend/apps/notebooks/tests/test_notebooks.py
backend/apps/notebooks/migrations/0001_initial.py
backend/apps/notebooks/migrations/0002_enable_rls.py
backend/apps/questions/views.py
backend/apps/questions/serializers.py
backend/apps/questions/tests/test_document_questions.py
backend/apps/ai_classroom/views.py
backend/apps/ai_classroom/serializers.py
backend/apps/ai_classroom/urls.py
backend/apps/ai_classroom/tests/test_tag_rename.py
backend/apps/jobs/migrations/0003_job_coalesced_from.py
backend/apps/accounts/services/budget.py
backend/shared/observability/metrics.py (extended)
backend/shared/observability/views.py (extended)
backend/providers/llm/chain.py (extended with D4/D5)
scripts/backup_offsite_hook.sh
docs/runbooks/backup_restore.md
```

### Backend (Modified)
```
backend/config/celery.py (beat_schedule)
backend/config/settings/base.py (CORS, CSRF, Redis, Prometheus, coalescing, budget env vars)
backend/config/urls.py (notebooks, ai_classroom, metrics)
backend/requirements.txt (django-cors-headers, django-redis, django-prometheus)
backend/apps/documents/views.py (AIBudgetThrottle on enrich/refresh-ai)
backend/apps/chat/views.py (AIBudgetThrottle on messages)
backend/shared/throttles.py (Decimal cost, AIBudgetThrottle integration)
backend/apps/audit/tasks.py (offsite hook invocation)
backend/apps/ai_classroom/services.py (coalescing logic)
backend/apps/jobs/models.py (coalesced_from FK)
```

### Frontend (New)
```
frontend/src/hooks/useOnlineStatus.ts
frontend/src/components/OfflineBanner.tsx
frontend/public/sw.js
frontend/src/state/useOutboxStore.ts
frontend/src/services/sync/outbox.ts (extended)
frontend/src/db/indexeddb/db.ts (extended)
```

### Frontend (Modified)
```
frontend/package.json (coverage script, @vitest/coverage-v8)
frontend/vite.config.ts (PWA config)
frontend/src/main.tsx (SW registration)
frontend/src/app/App.tsx (OfflineBanner)
```

### CI/CD (New)
```
.github/workflows/ci.yml
backend/pyproject.toml (coverage config)
docs/openapi/schema.yml (committed snapshot)
```

---

## Tests Added
- `backend/apps/notebooks/tests/test_notebooks.py` — 17 tests
- `backend/apps/questions/tests/test_document_questions.py` — 4 tests
- `backend/apps/ai_classroom/tests/test_tag_rename.py` — 6 tests

**Total: 27 new tests, all passing**