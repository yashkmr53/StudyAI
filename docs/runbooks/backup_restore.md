# Backup & Restore Runbook — StudyAI

**Architecture refs:** §70 (backup/restore), §75 (RPO/RTO targets)
**Gap refs:** A4 (scheduled backup automation), C2 (backup schedule/offsite/RPO-RTO)

---

## Targets

| Metric | Target | Notes |
|--------|--------|-------|
| RPO (Recovery Point Objective) | ≤ 24 hours | Daily backup at 02:30 UTC |
| RTO (Recovery Time Objective) | ≤ 4 hours | Manual pg_restore + smoke test |

---

## Automated Daily Backup (Production)

**Schedule:** Celery Beat → `daily_backup` task → 02:30 UTC daily
**Task:** `apps.core.tasks.daily_backup`
**Flow:**
1. Runs `python manage.py backup_database --output-dir /backups --format custom`
2. On success, invokes `scripts/backup_offsite_hook.sh --source-dir /backups --dest-uri <OFFSITE_URI>`
3. Logs outcome to Celery logs & `AuditLog` (action: `backup.completed` / `backup.failed`)

**Environment variables:**
```
OFFSITE_BACKUP_URI=s3://bucket/path   # or gs://, rsync://, etc.
BACKUP_RETENTION_DAYS=30              # local retention; offsite handles its own lifecycle
```

**Compose mount:** `/backups` volume mounted on `beat` and `api` services (see `docker-compose.yml`).

---

## Manual Backup (Ad-hoc)

```bash
# On any host with pg_dump access to the database
python manage.py backup_database --output-dir /tmp/manual_backup --format custom
# Output: /tmp/manual_backup/studyai_20260823_023000.dump
```

**Verify immediately:**
```bash
python manage.py verify_backup --backup-file /tmp/manual_backup/studyai_20260823_023000.dump
```

---

## Restore Procedure (Disaster Recovery)

**Prerequisites:**
- Clean PostgreSQL instance (can be same host, different DB name)
- Backup file (`.dump` custom format preferred)
- `psql` / `pg_restore` client tools

**Steps:**

1. **Create scratch database**
   ```bash
   createdb studyai_restore_20260823
   ```

2. **Restore**
   ```bash
   pg_restore -d studyai_restore_20260823 --no-owner /path/to/studyai_20260823_023000.dump
   ```

3. **Smoke test (row counts)**
   ```bash
   psql -d studyai_restore_20260823 -t -c "
     SELECT 'documents', count(*) FROM documents_document
     UNION ALL SELECT 'users', count(*) FROM accounts_user
     UNION ALL SELECT 'notes', count(*) FROM notespace_note
     UNION ALL SELECT 'chunks', count(*) FROM retrieval_notechunk;
   "
   ```

4. **Validate RTO**
   - Time from backup file → step 3 complete should be ≤ 4 hours for production-scale DB.

5. **Cutover (if promoting to production)**
   - Update `DATABASES['default']['NAME']` in Django settings
   - Run migrations: `python manage.py migrate --noinput`
   - Restart `api` and `worker` services

---

## Offsite Copy Integration (Production)

The `scripts/backup_offsite_hook.sh` is a **stub** in Phase 10. Replace with real implementation:

### Option A: AWS S3 (recommended)
```bash
#!/usr/bin/env bash
aws s3 sync "$SOURCE_DIR" "$DEST_URI" --storage-class GLACIER_IR
```
Set `OFFSITE_BACKUP_URI=s3://my-bucket/studyai-backups/`

### Option B: Google Cloud Storage
```bash
#!/usr/bin/env bash
gsutil -m rsync -r "$SOURCE_DIR" "$DEST_URI"
```
Set `OFFSITE_BACKUP_URI=gs://my-bucket/studyai-backups/`

### Option C: Rsync to remote host
```bash
#!/usr/bin/env bash
rsync -avz --delete "$SOURCE_DIR/" "user@backup-host:/path/to/backups/"
```
Set `OFFSITE_BACKUP_URI=rsync://user@backup-host/path/to/backups/`

**After implementing:** Test end-to-end by running the hook manually and verifying objects appear in destination.

---

## Retention & Cleanup

| Location | Policy | Implementation |
|----------|--------|----------------|
| Local (`/backups`) | 30 days | `find /backups -name '*.dump' -mtime +30 -delete` (cron or beat task) |
| Offsite (S3/GCS) | 90 days + Glacier | Bucket lifecycle rules (transition to Glacier after 30d, expire after 90d) |

**Add to beat_schedule** (Phase 11):
```python
"prune-local-backups": {
    "task": "apps.core.tasks.prune_local_backups",
    "schedule": crontab(hour=3, minute=0),  # after daily backup
},
```

---

## Verification Drills

**Quarterly (mandatory):**
1. Trigger manual backup on production DB
2. Restore to scratch DB in staging environment
3. Run full test suite against restored DB (`pytest -x`)
4. Document RTO actual time
5. Update this runbook if gaps found

**Monthly (automated):**
- `verify_backup` runs automatically after each daily backup (beat task chain)
- Alert on failure via monitoring (Phase 11: Sentry/Prometheus)

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `pg_dump: connection refused` | DB not reachable from beat container | Check `POSTGRES_HOST`, network, security groups |
| `pg_restore: could not connect` | Target DB doesn't exist | Create target DB first (`createdb`) |
| Offsite hook exits 2 | `SOURCE_DIR` missing | Verify beat mounts `/backups` volume |
| Backup > 24h old | Beat not running / task failed | `docker compose logs beat`; check `daily_backup` task logs |
| RTO exceeded | Large DB, slow network | Parallel restore (`pg_restore -j 4`); consider PITR / replicas |

---

## Contacts

| Role | Contact |
|------|---------|
| Primary DBA | (pending — Phase 11 input #6) |
| Platform/Infra | (pending — Phase 11 input #8) |
| On-call | (pending — Phase 11 input #9) |

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-08-23 | Initial version (Phase 10) | — |