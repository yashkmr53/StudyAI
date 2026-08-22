# Data Lifecycle — Phase 10

**Status:** Extended with backup automation, budget reset, outbox retention

---

## Data Categories & Retention

| Data Type | Retention | Deletion Policy | Notes |
|-----------|-----------|-----------------|-------|
| **Canonical Documents** | Indefinite | Never (immutable) | Source of truth |
| **Document Revisions** | Indefinite | Never (immutable) | Append-only |
| **Enriched Notes** | Indefinite | Soft delete (superseded flag) | Older versions retained |
| **OCR/Provider Logs** | Indefinite | Never | Audit trail |
| **Provider Call Logs** | Indefinite | Never | Budget accounting |
| **Jobs** | Indefinite | Soft delete (cancelled status) | Debugging |
| **Audit Logs** | Indefinite | Never | Compliance |
| **Outbox (Client)** | 30 days | Auto-cleanup | IndexedDB TTL |
| **Backups (Local)** | 30 days | Cron/beat task | `find -mtime +30 -delete` |
| **Backups (Offsite)** | 90 days | Bucket lifecycle | Glacier transition |
| **Monthly Budgets** | Rolling | Reset 1st of month | Counters zeroed |

---

## Backup Lifecycle (Phase 10)

### Local Backup
```
Daily 02:30 UTC
       │
       ▼
pg_dump → /backups/studyai_YYYYMMDD_HHMMSS.dump
       │
       ▼ (success)
Offsite Hook → $OFFSITE_BACKUP_URI
       │
       ▼
AuditLog: backup.completed / backup.failed
       │
       ▼ (30 days later)
Local Prune: find /backups -name '*.dump' -mtime +30 -delete
```

### Offsite Backup
```
S3/GCS/rsync
       │
       ▼
Bucket Lifecycle Rules:
  - Day 0: Standard
  - Day 30: Transition to Glacier/Archive
  - Day 90: Expire (delete)
```

---

## Budget Lifecycle (Phase 10)

### Monthly Budget Reset
```
1st of month 00:00 UTC (Celery Beat)
       │
       ▼
reset_monthly_budgets task
       │
       ▼
For each UserProfile:
  current_month_token_usage = 0
  current_month_cost_usd = 0
  budget_reset_date = 1st of next month
```

### Budget Enforcement
```
AI Request
       │
       ▼
BudgetService.check_and_increment()
       │
       ├─► _reset_if_needed() → resets if reset_date passed
       │
       ├─► Check token budget → 429 if exceeded
       │
       ├─► Check cost budget → 429 if exceeded
       │
       └─► Atomic increment counters
```

---

## Outbox Lifecycle (Phase 10)

### Client-Side (IndexedDB)
```
Stroke Created
       │
       ▼
queueOperation() → status=pending
       │
       ▼ (flushOutbox)
status=sending
       │
       ├─► Success → status=acknowledged, acknowledged_at set
       │
       └─► Failure → status=failed
                    │
                    ▼ (retry)
            status=retrying
                    │
                    ▼ (next flush)
            status=sending
```

### Retention
- **Pending/Sending/Retrying:** Until acknowledged or max retries
- **Failed:** Until retry or manual clear
- **Acknowledged:** 30 days TTL (configurable)
- **Max Operations:** No hard limit (IndexedDB quota)

---

## Provider Call Logs

### Retention
- **ProviderCallLog:** Indefinite (budget accounting, audit)
- **Fields:** provider, model, latency_ms, success, error, input_tokens, output_tokens, total_tokens, estimated_cost_usd, metadata (redactions_count)

### Monthly Aggregation (Phase 11)
```
Daily → Monthly rollup
  total_calls, total_tokens, total_cost, success_rate, fallback_rate
```

---

## Document Lifecycle (Existing, Unchanged)

```
Upload → OCR → Revisions → Enrichment → Questions/Tags/Tests
   │         │        │           │              │
   ▼         ▼        ▼           ▼              ▼
Canonical  Search  Immutable  Generated    Revision-aware
Layer      Index   History    Artifacts    Content
```

---

## Cleanup Procedures

### Manual Cleanup (If Needed)
```bash
# Expired outbox (client-side)
# Run in browser console:
indexedDB.open("studyai").then(db => {
  const tx = db.transaction("outbox", "readwrite");
  const store = tx.objectStore("outbox");
  const index = store.index("by_status");
  index.openCursor(IDBKeyRange.only("acknowledged")).onsuccess = e => {
    const cursor = e.target.result;
    if (cursor) {
      const age = Date.now() - new Date(cursor.value.acknowledged_at).getTime();
      if (age > 30 * 24 * 60 * 60 * 1000) cursor.delete();
      cursor.continue();
    }
  };
});

# Local backups
find /backups -name '*.dump' -mtime +30 -delete

# Database vacuum (PostgreSQL)
VACUUM ANALYZE;
```

---

## GDPR / Data Subject Rights

### Deletion Request
1. Soft-delete user: `is_active=False`
2. Anonymize: email → `deleted_<id>@example.com`
3. Retain: canonical documents (legal hold), audit logs
4. Remove: outbox, sessions, tokens

### Anonymization (Phase 11)
```
User Profile
       │
       ▼
Anonymize PII: email, name
       │
       ▼
Retain: document ownership (FK to profile)
       │
       ▼
Remove: outbox, tokens, sessions
```

---

## Phase 11 Enhancements

| Feature | Description |
|---------|-------------|
| Automated local backup pruning | Beat task `prune-local-backups` |
| Offsite backup verification | Monthly restore drill automation |
| Provider cost aggregation | Monthly rollup tables |
| GDPR anonymization flow | `anonymize_user` management command |
| Outbox TTL enforcement | Automatic cleanup job |
| Backup encryption | pg_dump with `--encrypt` |

---

## Related Documentation

- `docs/phase_10/operations/BACKUP_AND_RECOVERY.md` — Backup procedures
- `docs/phase_10/operations/TESTING.md` — Data cleanup tests
- `docs/phase_6/operations/DATA_LIFECYCLE.md` — Base specification