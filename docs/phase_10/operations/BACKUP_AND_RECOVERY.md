# Backup & Recovery — Phase 10

**Status:** Automated daily backup with offsite hook stub; runbook documented

---

## Automation

### Schedule
- **When:** 02:30 UTC daily (via Celery Beat `daily_backup` task)
- **Task:** `apps.audit.tasks.daily_backup`
- **Output:** `/backups/studyai_YYYYMMDD_HHMMSS.dump` (pg_dump custom format)

### Offsite Copy
- **Hook:** `scripts/backup_offsite_hook.sh --source-dir /backups --dest-uri $OFFSITE_BACKUP_URI`
- **Called:** After successful pg_dump
- **Failure:** Logged + alerted; does not retry (backup itself succeeded)

### Environment
```bash
OFFSITE_BACKUP_URI=s3://bucket/path   # or gs://, rsync://
BACKUP_RETENTION_DAYS=30              # local retention
```

### Compose Mount
`/backups` volume mounted on `beat` and `api` services

---

## Manual Operations

### Create Backup
```bash
python manage.py backup_database --output-dir /tmp/manual_backup --format custom
# Output: /tmp/manual_backup/studyai_20260823_023000.dump
```

### Verify Backup
```bash
python manage.py verify_backup --backup-file /tmp/manual_backup/studyai_20260823_023000.dump
```

### List Backups
```bash
ls -lh /backups/
```

---

## Recovery Procedure

### Prerequisites
- Clean PostgreSQL instance (can be same host, different DB name)
- Backup file (`.dump` custom format)
- `pg_restore` client tools

### Steps

1. **Create Scratch Database**
   ```bash
   createdb studyai_restore_20260823
   ```

2. **Restore**
   ```bash
   pg_restore -d studyai_restore_20260823 --no-owner /path/to/studyai_20260823_023000.dump
   ```

3. **Smoke Test**
   ```bash
   psql -d studyai_restore_20260823 -t -c "
     SELECT 'documents', count(*) FROM documents_document
     UNION ALL SELECT 'users', count(*) FROM accounts_user
     UNION ALL SELECT 'notes', count(*) FROM notespace_note
     UNION ALL SELECT 'chunks', count(*) FROM retrieval_notechunk;
   "
   ```

4. **Validate RTO**
   - Target: ≤ 4 hours for production-scale DB

5. **Cutover (if promoting to production)**
   - Update `DATABASES['default']['NAME']` in Django settings
   - Run migrations: `python manage.py migrate --noinput`
   - Restart `api` and `worker` services

---

## Retention & Cleanup

| Location | Policy | Implementation |
|----------|--------|----------------|
| Local (`/backups`) | 30 days | `find /backups -name '*.dump' -mtime +30 -delete` (cron or beat task) |
| Offsite (S3/GCS) | 90 days + Glacier | Bucket lifecycle rules (transition after 30d, expire after 90d) |

### Phase 11: Automated Local Pruning
Add to `beat_schedule`:
```python
"prune-local-backups": {
    "task": "apps.core.tasks.prune_local_backups",
    "schedule": crontab(hour=3, minute=0),  # after daily backup
},
```

---

## Verification Drills

### Quarterly (Mandatory)
1. Trigger manual backup on production DB
2. Restore to scratch DB in staging
3. Run full test suite: `pytest -x`
4. Document actual RTO
5. Update runbook if gaps found

### Monthly (Automated)
- `verify_backup` runs after each daily backup (beat task chain)
- Alert on failure via monitoring (Phase 11)

---

## Targets

| Metric | Target | Notes |
|--------|--------|-------|
| RPO (Recovery Point Objective) | ≤ 24 hours | Daily backup at 02:30 UTC |
| RTO (Recovery Time Objective) | ≤ 4 hours | Manual pg_restore + smoke test |

---

## Runbook Location
Full runbook: `docs/runbooks/backup_restore.md`

---

## Related Documentation

- `docs/runbooks/backup_restore.md` — Detailed procedures
- `docs/phase_10/architecture/SYSTEM_FLOWS.md` — Backup flow diagram
- `docs/phase_6/operations/BACKUP_AND_RECOVERY.md` — Base specification