# System Flows — Phase 10

**Date:** 2026-08-23

---

## 1. Scheduler Flow (C1)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Celery Beat │────►│ Redis Broker│────►│   Workers   │
│  (beat)     │     │   (DB 0)    │     │ (consume)   │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       │ beat_schedule:
       ├─► reap_stuck_jobs (5m) ──► reap_stuck_jobs_task
       ├─► promote_retries (2m) ──► promote_retries_task
       ├─► daily_backup (02:30) ──► daily_backup task
       └─► reset_monthly_budgets (1st) ──► reset_monthly_budgets
```

### Task Details

| Task | Schedule | Action |
|------|----------|--------|
| `reap_stuck_jobs_task` | 5 min | Reset RUNNING jobs stuck > timeout to QUEUED |
| `promote_retries_task` | 2 min | Promote FAILED_RETRYABLE with `next_retry_at <= now` to QUEUED |
| `daily_backup` | 02:30 UTC | pg_dump → `/backups` → invoke offsite hook |
| `reset_monthly_budgets` | 1st 00:00 UTC | Zero `current_month_token_usage` and `current_month_cost_usd` |

---

## 2. Backup Automation Flow (C2, A4)

```
daily_backup task
       │
       ▼
┌─────────────────────────────┐
│ pg_dump -Fc → /backups/     │
│ studyai_YYYYMMDD_HHMMSS.dump│
└─────────────────────────────┘
       │
       ▼ (success)
┌─────────────────────────────┐
│ backup_offsite_hook.sh      │
│ --source-dir /backups       │
│ --dest-uri $OFFSITE_URI     │
└─────────────────────────────┘
       │
       ├─► S3: aws s3 sync --storage-class GLACIER_IR
       ├─► GCS: gsutil -m rsync -r
       └─► rsync: rsync -avz --delete
       │
       ▼ (failure logged, alerted)
┌─────────────────────────────┐
│ AuditLog: backup.completed  │
│ AuditLog: backup.failed     │
└─────────────────────────────┘
```

### Manual Drill
```bash
# Backup
python manage.py backup_database --output-dir /tmp/test --format custom

# Verify
python manage.py verify_backup --backup-file /tmp/test/studyai_20260823_023000.dump
```

---

## 3. Security Hardening Flows

### 3.1 Request Processing with CORS/CSRF/Throttle
```
Request
   │
   ├─► CorsMiddleware (CORS_ALLOWED_ORIGINS)
   │       ├─► OPTIONS → 200 + CORS headers
   │       └─► Other → continue
   │
   ├─► CsrfViewMiddleware (CSRF_TRUSTED_ORIGINS)
   │       └─► POST/PUT/PATCH → validate CSRF token
   │
   ├─► LiveSettingsScopedRateThrottle / AIBudgetThrottle
   │       ├─► Redis throttle cache (DB 2)
   │       │       └─► Rate limit exceeded → 429 RATE_LIMITED
   │       │
   │       └─► AIBudgetThrottle (if ai scope)
   │               └─► BudgetService.check_and_increment()
   │                       ├─► Budget exceeded → 429 with budget details
   │                       └─► OK → continue
   │
   └─► View processing
```

### 3.2 LLM Provider Call with Prompt-Injection + Data-Minimization
```
LLMChainProvider.generate_structured()
   │
   ├─► For each provider in chain:
   │       │
   │       ├─► Build system prompt:
   │       │       original_system + "\n\n" + PROMPT_INJECTION_DIRECTIVE
   │       │
   │       ├─► Sanitize user prompt:
   │       │       _sanitize_for_provider(user_prompt)
   │       │       ├─► Truncate to MAX_PROVIDER_INPUT_CHARS
   │       │       ├─► Redact: email, phone, credit card, SSN
   │       │       └─► Returns (sanitized_text, redaction_count)
   │       │
   │       ├─► Call provider.generate_structured()
   │       │
   │       ├─► On success:
   │       │       record_provider_call(success=True, redactions_count=...)
   │       │
   │       └─► On failure:
   │               record_provider_call(success=False, redactions_count=0)
   │               Try next provider
   │
   └─► All failed → raise ProviderError (502)
```

---

## 4. Enrichment Coalescing Flow (B7)

```
POST /documents/{id}/enrich
   │
   ▼
EnrichmentService.enqueue_enrichment()
   │
   ├─► Check existing non-stale EnrichedNote
   │       └─► Found → return existing (200)
   │
   ├─► Check daily budget (AIBudgetThrottle)
   │       └─► Exceeded → 429 RATE_LIMITED
   │
   ├─► COALESCING CHECK (if not force_refresh):
   │       │
   │       ├─► Find pending enrichment job within coalesce_window
   │       │       (Job.status IN [QUEUED, RUNNING], created_at >= now - window)
   │       │
   │       ├─► If found:
   │       │       │
   │       │       ├─► Compute change magnitude
   │       │       │       (placeholder: 0.5; real: cosine similarity of embeddings)
   │       │       │
   │       │       ├─► magnitude <= threshold → return existing job (coalesced=True)
   │       │       │
   │       │       └─► magnitude > threshold → create new job
   │       │
   │       └─► No pending job → create new job
   │
   └─► Create/get Job with idempotency_key
           │
           ├─► If created or retryable/dead_letter:
           │       Reset status → QUEUED
           │       dispatch_job()
           │
           └─► Return {note: None, job: Job, created: bool, coalesced: bool}
```

---

## 5. Monthly Budget Enforcement (B8)

```
AI Request (enrich / refresh-ai / chat)
   │
   ▼
AIBudgetThrottle.allow_request()
   │
   ├─► Standard rate limit (Redis throttle cache)
   │       └─► Exceeded → return False → 429
   │
   └─► BudgetService.check_and_increment(user, est_tokens, est_cost)
           │
           ├─► Get/create UserProfile
           │
           ├─► _reset_if_needed()
           │       └─► If budget_reset_date <= now:
           │               current_month_token_usage = 0
           │               current_month_cost_usd = 0
           │               budget_reset_date = 1st of next month
           │
           ├─► Check token budget:
           │       new_usage = current + est_tokens
           │       new_usage > monthly_token_budget → BudgetExceeded("token")
           │
           ├─► Check cost budget:
           │       new_cost = current + est_cost
           │       new_cost > monthly_cost_budget_usd → BudgetExceeded("cost")
           │
           └─► Atomic increment:
                   UserProfile.objects.update(
                       current_month_token_usage=new_usage,
                       current_month_cost_usd=new_cost
                   )
```

---

## 6. Frontend Offline Flows

### 6.1 Online/Offline Detection (G5)
```
Component mounts
   │
   ▼
useOnlineStatus()
   │
   ├─► Initial: navigator.onLine
   │
   ├─► window.addEventListener('online', () => setIsOnline(true), setWasOffline(true))
   │
   └─► window.addEventListener('offline', () => setIsOnline(false))
   │
   ▼
OfflineBanner renders:
   │
   ├─► isOnline=true, wasOffline=false → null
   ├─► isOnline=false → "You are offline..."
   └─► isOnline=true, wasOffline=true → "Connection restored. Syncing..."
```

### 6.2 Service Worker Background Sync (G6)
```
Offline: User creates stroke
   │
   ▼
queueOperation() → IndexedDB outbox (status=pending)
   │
   ▼ (later, connectivity restored)
Service Worker: sync event (tag=outbox-flush)
   │
   ▼
flushOutboxFromSW()
   │
   ├─► Read pending ops from IndexedDB
   │
   ├─► Group by session+page
   │
   ├─► Mark ops as sending
   │
   ├─► PostMessage to main thread (MessageChannel)
   │       │
   │       ├─► Main thread: canvasApi.pushStrokes()
   │       │       └─► On success: mark ops acknowledged
   │       │       └─► On failure: mark ops failed
   │       │
   │       └─► SW waits for response via port1.onmessage
   │
   └─► All groups done → sync complete
```

### 6.3 Outbox State Transitions (G7)
```
┌─────────┐     flushOutbox()      ┌──────────┐
│ pending │ ─────────────────────► │ sending  │
└─────────┘                         └──────────┘
       │                                   │
       │                                   ├─► Success ──► acknowledged
       │                                   │
       │                                   └─► Failure ──► failed
       │                                             │
       │                                             ▼
       │                                    ┌───────────┐
       │                                    │ retrying  │
       │                                    └───────────┘
       │                                             │
       └─────────────── retryFailedOperations() ◄────┘
```

---

## 7. Prometheus Metrics Collection (E)

```
Application Code
   │
   ├─► ocr_fallback_inc(provider, reason)
   ├─► schema_validation_failure_inc(endpoint, field)
   ├─► retrieval_latency_observe(query_type, seconds)
   ├─► evaluation_score_set(metric, dataset, value)
   ├─► product_usage_inc(feature, action)
   │
   ▼
Prometheus Client (in-process)
   │
   ├─► Counter: ocf_fallback_total{provider,reason}
   ├─► Counter: schema_validation_failure_total{endpoint,field}
   ├─► Histogram: retrieval_latency_seconds{query_type}
   ├─► Gauge: evaluation_score{metric,dataset}
   ├─► Counter: product_usage_total{feature,action}
   │
   ▼
GET /metrics
   │
   ▼
Prometheus Scraping (external)
```

### Metric Definitions

| Metric | Type | Labels | When Incremented |
|--------|------|--------|------------------|
| `ocr_fallback_total` | Counter | provider, reason | OCR fallback attempted |
| `schema_validation_failure_total` | Counter | endpoint, field | JSON schema validation fails |
| `retrieval_latency_seconds` | Histogram | query_type | Each retrieval query |
| `evaluation_score` | Gauge | metric, dataset | Eval harness runs |
| `product_usage_total` | Counter | feature, action | User actions (create_note, enrich, etc.) |

---

## 8. CI/CD Flow (H)

```
Push / PR
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions CI                        │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   Backend    │  Frontend    │   Docker     │ OpenAPI Drift  │
├──────────────┼──────────────┼──────────────┼────────────────┤
│ 1. Checkout  │ 1. Checkout  │ 1. Checkout  │ 1. Checkout    │
│ 2. Setup py  │ 2. Setup node│ 2. Build     │ 2. Setup py    │
│ 3. Install   │ 3. npm ci    │ 3. Compose up│ 3. Install     │
│    deps      │ 4. tsc       │ 4. Health    │ 4. Generate    │
│ 4. Migrate   │ 5. test      │    checks    │    schema      │
│ 5. pytest    │    + coverage│ 5. Compose   │ 5. git diff    │
│    + coverage│ 6. build     │    down      │    --exit-code │
│ 6. coverage  │              │              │                │
│    report    │              │              │                │
│ 7. OpenAPI   │              │              │                │
│    drift     │              │              │                │
└──────────────┴──────────────┴──────────────┴────────────────┘
   │
   ▼
All jobs must pass → Merge allowed
```

### Coverage Gates
- Backend: `coverage report --fail-under=80`
- Frontend: `vitest --coverage` with 70% threshold

---

## 9. Tag Rename Flow (B4)

```
POST /api/v1/tags/{id}/rename/
Body: { "name": "New Name" }
   │
   ▼
TagViewSet.rename()
   │
   ├─► get_object() → Tag (owner-scoped via subject)
   │
   ├─► Validate: name not empty, ≤120 chars
   │
   ├─► TaggingService.rename_tag(tag, new_name)
   │       │
   │       ├─► Update tag.display_name
   │       │
   │       └─► TagChangeLog.create(
   │               change_type=RENAMED,
   │               old_value=old_name,
   │               new_value=new_name
   │           )
   │
   └─► Return updated Tag (200)
```

---

## 10. Document Questions Flow (B2)

```
GET /api/v1/documents/{id}/questions
   │
   ▼
DocumentQuestionsViewSet.list()
   │
   ├─► Verify document exists + owned by user
   │       └─► 404 if not found or not owned
   │
   ├─► Filter Question.objects by document_id
   │       └─► Select related for efficiency
   │
   └─► Paginate + serialize
           │
           └─► Response: { results: [QuestionSerializer...] }
```

---

## Related Documentation

- `docs/phase_10/architecture/ARCHITECTURE.md` — Component diagrams
- `docs/phase_10/architecture/TRACEABILITY.md` — Gap-to-code mapping
- `docs/phase_10/PHASE_10_IMPLEMENTATION_PLAN.md` — Implementation details