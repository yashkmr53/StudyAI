# Background Jobs — Phase 10

**Status:** Extended with scheduler, budget reset, backup automation

---

## Celery Beat Schedule

**File:** `backend/config/celery.py`

```python
app.conf.beat_schedule = {
    "reap-stuck-jobs": {
        "task": "apps.jobs.tasks.reap_stuck_jobs_task",
        "schedule": 300.0,  # 5 minutes
    },
    "promote-retries": {
        "task": "apps.jobs.tasks.promote_retries_task",
        "schedule": 120.0,  # 2 minutes
    },
    "daily-backup": {
        "task": "apps.audit.tasks.daily_backup",
        "schedule": crontab(hour=2, minute=30),  # 02:30 UTC
    },
    "reset-monthly-budgets": {
        "task": "apps.accounts.tasks.reset_monthly_budgets",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),  # 1st of month
    },
}
```

---

## Task Definitions

### `reap_stuck_jobs_task` (`apps.jobs.tasks`)
**Schedule:** Every 5 minutes
**Action:** Reset RUNNING jobs stuck > `JOBS_TIMEOUT_SECONDS` to QUEUED
**Logic:**
```python
stuck = Job.objects.filter(
    status=Job.Status.RUNNING,
    started_at__lt=timezone.now() - timedelta(seconds=JOBS_TIMEOUT_SECONDS)
)
stuck.update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
```

### `promote_retries_task` (`apps.jobs.tasks`)
**Schedule:** Every 2 minutes
**Action:** Promote FAILED_RETRYABLE with `next_retry_at <= now` to QUEUED
**Logic:**
```python
due = Job.objects.filter(
    status=Job.Status.FAILED_RETRYABLE,
    next_retry_at__lte=timezone.now()
)
for job in due:
    job.status = Job.Status.QUEUED
    job.next_retry_at = None
    job.save()
    dispatch_job(job)
```

### `daily_backup` (`apps.audit.tasks`)
**Schedule:** 02:30 UTC daily
**Action:** pg_dump → `/backups` → offsite hook
**Logic:**
```python
@task(bind=True, max_retries=2, default_retry_delay=300)
def daily_backup(self):
    pg_dump → /backups/studyai_YYYYMMDD_HHMMSS.dump
    if OFFSITE_BACKUP_URI:
        subprocess.run([/backup_offsite_hook.sh, --source-dir, /backups, --dest-uri, $OFFSITE_BACKUP_URI])
    AuditLog.create(action="backup.completed" / "backup.failed")
```

### `reset_monthly_budgets` (`apps.accounts.tasks`)
**Schedule:** 1st of month, 00:00 UTC
**Action:** Zero monthly budget counters for all profiles
**Logic:**
```python
@task
def reset_monthly_budgets():
    UserProfile.objects.update(
        current_month_token_usage=0,
        current_month_cost_usd=0,
        budget_reset_date=first_of_next_month()
    )
```

---

## Job Model (Extended)

### `jobs_job` Table
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | PK |
| job_type | VARCHAR(100) | enrich, ocr, pdf_render, etc. |
| resource_type | VARCHAR(100) | document, notebook, etc. |
| resource_id | CHAR(64) | Resource UUID |
| profile_id | UUID | Owner profile |
| revision_id | UUID | Source revision (nullable) |
| idempotency_key | VARCHAR(255) | Unique, prevents duplicates |
| status | VARCHAR(32) | QUEUED, RUNNING, FAILED_RETRYABLE, FAILED_DEAD_LETTER, CANCELLING, CANCELLED, SUCCEEDED |
| attempt_count | INTEGER | Incremented on each run |
| next_retry_at | TIMESTAMPTZ | For FAILED_RETRYABLE |
| last_error | TEXT | Error message |
| started_at | TIMESTAMPTZ | When RUNNING |
| finished_at | TIMESTAMPTZ | When terminal |
| created_at | TIMESTAMPTZ | Auto |
| **coalesced_from_id** | UUID | FK → self (nullable, B7) |

### Status Transitions
```
QUEUED → RUNNING (claim)
RUNNING → SUCCEEDED (mark_succeeded)
RUNNING → FAILED_RETRYABLE (mark_retryable, if attempt < max)
RUNNING → FAILED_DEAD_LETTER (dead_letter, if attempt >= max)
QUEUED/RUNNING → CANCELLING (cancel_job)
CANCELLING → CANCELLED
FAILED_RETRYABLE → QUEUED (promote_retries_task)
FAILED_DEAD_LETTER → QUEUED (manual retry via admin)
```

---

## Enrichment Coalescing (B7)

### Job Coalescing Logic
```python
def enqueue_enrichment(user, document_id, force_refresh=False):
    # ... existing checks ...
    
    if not force_refresh and coalesce_window > 0:
        since = now - timedelta(seconds=coalesce_window)
        pending = Job.objects.filter(
            job_type="enrich",
            resource_type="document",
            resource_id=document_id,
            status__in=[QUEUED, RUNNING],
            created_at__gte=since
        ).order_by("-created_at").first()
        
        if pending:
            magnitude = compute_change_magnitude(document)
            if magnitude <= change_threshold:
                return {"job": pending, "created": False, "coalesced": True}
    
    # Create new job with coalesced_from
    job, created = get_or_create_job(...)
    if not created and pending:
        job.coalesced_from = pending
        job.save()
```

### Coalescing Parameters
| Setting | Default | Description |
|---------|---------|-------------|
| `ENRICHMENT_COALESCE_WINDOW_SECONDS` | 300 | Time window to check for pending jobs |
| `ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD` | 0.15 | Cosine similarity threshold (0-1) |

---

## Budget Reset Job

### `reset_monthly_budgets` Task
**Schedule:** 1st of month, 00:00 UTC
**Logic:**
```python
@task
def reset_monthly_budgets():
    now = timezone.now()
    if now.month == 12:
        next_reset = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_reset = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    UserProfile.objects.update(
        current_month_token_usage=0,
        current_month_cost_usd=Decimal("0"),
        budget_reset_date=next_reset,
    )
```

### Monthly Budget Model
| Field | Type | Default |
|-------|------|---------|
| monthly_token_budget | INTEGER | 100000 |
| monthly_cost_budget_usd | DECIMAL(10,2) | 50.00 |
| current_month_token_usage | INTEGER | 0 |
| current_month_cost_usd | DECIMAL(10,2) | 0 |
| budget_reset_date | TIMESTAMPTZ | 1st of next month |

---

## Worker Configuration

### Docker Compose
```yaml
worker:
  build: ./backend
  command: celery -A config worker -l info
  # Same as beat, no separate beat service needed if beat disabled

beat:
  build: ./backend
  command: celery -A config beat -l info
```

### Concurrency
- Worker: Default prefork (CPU cores)
- Beat: Single process (scheduler)

---

## Monitoring

### Job Metrics (Status Endpoint)
```
/api/v1/status (staff only)
{
  "jobs": {
    "by_status": {"queued": 5, "running": 2, "succeeded": 100, ...},
    "by_type_status": {"enrich:queued": 3, "ocr:running": 1, ...},
    "queue_depth": 5,
    "dead_letter_count": 0,
    "retryable_count": 2,
    "created_last_24h": 50,
    "retried_last_24h": 3,
  }
}
```

### Prometheus Metrics
| Metric | Type | Labels |
|--------|------|--------|
| `jobs_total` | Counter | status, job_type |
| `job_duration_seconds` | Histogram | job_type |
| `job_retries_total` | Counter | job_type |

---

## Related Documentation

- `docs/phase_10/architecture/SYSTEM_FLOWS.md` — Scheduler flow
- `docs/phase_10/operations/OBSERVABILITY.md` — Job metrics
- `docs/phase_10/operations/TROUBLESHOOTING.md` — Job debugging
- `docs/phase_6/backend/BACKGROUND_JOBS.md` — Base specification