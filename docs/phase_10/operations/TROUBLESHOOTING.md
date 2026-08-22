# Troubleshooting — Phase 10

**Status:** Common issues and resolutions for Phase 10 components

---

## Scheduler (Celery Beat)

### Beat Not Starting
```
Symptom: docker compose ps shows beat exited
Check: docker compose logs beat
Common causes:
  - Redis not ready: ensure redis healthcheck passes
  - Migration pending: run python manage.py migrate
  - Import error: check celery.py syntax
```

### Tasks Not Running
```
Symptom: No task logs in beat output
Check:
  - beat_schedule syntax in celery.py
  - Task names match registered tasks (apps.jobs.tasks.xxx)
  - Timezone: beat uses UTC by default
```

### Backup Task Failing
```
Symptom: daily_backup task fails
Check: docker compose logs beat | grep daily_backup
Common causes:
  - pg_dump not in PATH: ensure postgresql-client in container
  - /backups not writable: check volume mount permissions
  - Database connection: verify POSTGRES_* env vars
```

---

## Security Hardening

### CORS Errors
```
Symptom: "CORS policy blocked" in browser console
Check:
  - CORS_ALLOWED_ORIGINS includes frontend origin
  - CorsMiddleware BEFORE CommonMiddleware in MIDDLEWARE
  - Credentials: if using cookies, CORS_ALLOW_CREDENTIALS=True
```

### CSRF Failures
```
Symptom: 403 Forbidden on POST from frontend
Check:
  - CSRF_TRUSTED_ORIGINS includes frontend origin
  - Frontend sends CSRF token (or uses cookie auth)
  - Session cookie domain matches
```

### Rate Limiting Issues
```
Symptom: Unexpected 429 RATE_LIMITED
Check:
  - Redis throttle cache (DB 2) has keys: redis-cli -n 2 KEYS "*"
  - DEFAULT_THROTTLE_RATES in settings
  - RATE_LIMITING_ENABLED=True
  - Multiple workers: must use Redis, not LocMemCache
```

### CSP Violations
```
Symptom: "Content-Security-Policy violated" in console
Check:
  - SecurityHeadersMiddleware CSP policy
  - 'unsafe-inline' for styles (React)
  - connect-src includes ws: wss: for WebSocket
  - Static assets served with same CSP (nginx config)
```

---

## Budget & Throttling

### Unexpected 429 on AI Requests
```
Symptom: 429 with budget details on enrich/chat
Response: {"error": {"code": "RATE_LIMITED", "details": {"budget_type": "token", "limit": "100000", "current": "100050"}}}
Fix:
  - Check UserProfile.monthly_token_budget (default 100000)
  - Check current_month_token_usage
  - Admin can increase per-user budget
  - Wait for monthly reset (1st of month 00:00 UTC)
```

### Budget Not Resetting
```
Symptom: Budget exhausted but should have reset
Check:
  - UserProfile.budget_reset_date field
  - BudgetService._reset_if_needed() logic
  - Timezone: uses UTC
```

---

## Enrichment Pipeline

### Enrichment Not Starting
```
Symptom: POST /enrich returns 200 existing note or 202 but job stuck
Check:
  - Document has completed revisions (current_revision_id not null)
  - Profile has budget remaining
  - Job created: check Job table for job_type="enrich"
  - Worker logs: docker compose logs worker | grep enrich
```

### Coalescing Not Working
```
Symptom: New enrichment job created despite recent edit
Check:
  - ENRICHMENT_COALESCE_WINDOW_SECONDS (default 300)
  - ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD (default 0.15)
  - Placeholder magnitude computation returns 0.5
  - Real implementation needs embedding comparison
```

### Enrichment Failing Silently
```
Symptom: Job status FAILED_DEAD_LETTER
Check:
  - Job.last_error field
  - ProviderCallLog for provider failures
  - Mock LLM may return malformed JSON
  - Schema validation errors in pipeline stages
```

---

## Frontend Offline

### Service Worker Not Registering
```
Symptom: No SW in chrome://serviceworker-internals
Check:
  - public/sw.js exists in build output
  - vite.config.ts has vite-plugin-pwa
  - Registration code in main.tsx
  - HTTPS or localhost (SW requires secure context)
```

### Background Sync Not Triggering
```
Symptom: Outbox not flushing on reconnect
Check:
  - Background Sync API support (not in Safari)
  - SW sync event listener registered
  - MessageChannel communication with main thread
  - Fallback: timer-based flush in outbox store
```

### Outbox Stuck in Failed
```
Symptom: Operations show failed, not retrying
Check:
  - useOutboxStore.retry() called
  - retryFailedOperations() transitions to retrying
  - Next flushOutbox() picks up retrying ops
  - Network errors vs 4xx/5xx handling
```

---

## Prometheus Metrics

### /metrics Returns 404
```
Symptom: GET /metrics → 404
Check:
  - PROMETHEUS_METRICS_ENABLED=true in env
  - django-prometheus in requirements
  - MetricsView in urls.py
```

### No Metrics Appearing
```
Symptom: /metrics returns empty or minimal
Check:
  - prometheus_client installed
  - Helper functions called (ocr_fallback_inc, etc.)
  - _init_prometheus_metrics() called on first use
```

---

## Database & Migrations

### Migration Fails
```
Symptom: python manage.py migrate fails
Common:
  - RLS policy on unsupported DB (SQLite): no-op, safe to ignore
  - Unique constraint violation: check existing data
  - FK to missing table: check dependency order
```

### RLS Not Working
```
Symptom: User sees other user's data
Check:
  - PostgreSQL (RLS no-op on SQLite)
  - ALTER TABLE ... ENABLE ROW LEVEL SECURITY
  - Policy uses current_setting('app.current_profile_id', true)
  - Middleware sets app.current_profile_id per request
```

---

## Docker/Deployment

### Container Won't Start
```
Check:
  - docker compose logs <service>
  - Healthcheck failing: verify endpoint
  - Volume permissions: /backups, /var/objectstore
  - Env vars: check .env file loaded
```

### Compose Up Hangs
```
Check:
  - Database not ready: depends_on condition: service_healthy
  - Redis not ready: check redis healthcheck
  - Port conflicts: 80, 8000, 5432, 6379
```

---

## Related Documentation

- `docs/phase_10/operations/TESTING.md` — Test debugging
- `docs/phase_10/operations/BACKUP_AND_RECOVERY.md` — Backup issues
- `docs/phase_6/operations/TROUBLESHOOTING.md` — Base troubleshooting