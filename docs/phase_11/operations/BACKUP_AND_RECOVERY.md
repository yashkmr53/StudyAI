# Phase 11 — Operations: Backup and Recovery

**Date:** 2026-08-23

---

## Overview

Phase 11 enhances backup with MinIO/S3 storage support. Backup can target local filesystem, MinIO, or S3 independently of application storage.

---

## Backup Commands

### Create Backup
```bash
# Local filesystem (legacy)
python manage.py backup_database --output-dir /tmp/backup --compress

# MinIO (local dev)
python manage.py backup_database --output-dir s3://studyai-backups/2024-01-15 --compress

# S3 (production)
python manage.py backup_database --output-dir s3://studyai-prod-backups/2024-01-15 --compress
```

### Verify Backup
```bash
# Local
python manage.py verify_backup --backup-dir /tmp/backup

# MinIO/S3
python manage.py verify_backup --backup-dir s3://studyai-backups/2024-01-15
```

### Automated Backup (Celery Beat)
```python
# config/celery.py
beat_schedule = {
    'daily-backup': {
        'task': 'apps.core.tasks.backup_database',
        'schedule': crontab(hour=2, minute=30),  # 02:30 UTC daily
        'kwargs': {
            'output_dir': 's3://studyai-backups/{{ ds }}',
            'compress': True
        }
    }
}
```

---

## Backup to MinIO (Local Dev)

### Configuration
```bash
# Separate bucket for backups (optional)
MINIO_BACKUP_BUCKET=studyai-backups
```

### Backup Script
```bash
#!/bin/bash
# scripts/backup_database_minio.sh

set -e

DATE=$(date +%Y-%m-%d)
BUCKET="${MINIO_BACKUP_BUCKET:-studyai-backups}"
PREFIX="${DATE}"

# Create backup locally
python manage.py backup_database --output-dir /tmp/backup_${DATE} --compress

# Upload to MinIO
mc mirror /tmp/backup_${DATE} minio/${BUCKET}/${PREFIX}

# Cleanup
rm -rf /tmp/backup_${DATE}

echo "Backup uploaded to minio://${BUCKET}/${PREFIX}"
```

### Offsite Hook (Phase 10)
```bash
# scripts/backup_offsite_hook.sh
#!/bin/bash
# Called by beat after backup_database completes

SOURCE_DIR=$1
DEST_URI=$2  # s3://bucket/path or minio://bucket/path

if [[ $DEST_URI == s3://* ]]; then
  aws s3 sync $SOURCE_DIR $DEST_URI
elif [[ $DEST_URI == minio://* ]]; then
  mc mirror $SOURCE_DIR ${DEST_URI/minio:\/\//minio/}
else
  echo "Unknown destination URI scheme: $DEST_URI"
  exit 1
fi
```

---

## Backup to S3 (Production)

### IAM Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::studyai-prod-backups",
        "arn:aws:s3:::studyai-prod-backups/*"
      ]
    }
  ]
}
```

### Cross-Region Replication (Optional)
```bash
# For RPO < 24h, enable cross-region replication
aws s3control put-bucket-replication --bucket studyai-prod-backups --replication-configuration file://replication.json
```

---

## Restore Procedure

### From Local Filesystem
```bash
# 1. Stop application
docker compose stop api worker beat

# 2. Restore database
python manage.py restore_database --backup-dir /tmp/backup_2024-01-15

# 3. Restore media files (if separate)
rsync -av /tmp/backup_2024-01-15/media/ /app/media/

# 4. Start application
docker compose start api worker beat
```

### From MinIO
```bash
# 1. Download from MinIO
mc mirror minio/studyai-backups/2024-01-15 /tmp/restore_2024-01-15

# 2. Restore
python manage.py restore_database --backup-dir /tmp/restore_2024-01-15
```

### From S3
```bash
# 1. Download from S3
aws s3 sync s3://studyai-prod-backups/2024-01-15 /tmp/restore_2024-01-15

# 2. Restore
python manage.py restore_database --backup-dir /tmp/restore_2024-01-15
```

---

## RPO/RTO Targets

| Environment | RPO | RTO | Backup Frequency | Storage |
|-------------|-----|-----|------------------|---------|
| Local Dev | 24h | 4h | Daily (manual) | MinIO |
| Staging | 12h | 2h | Daily (auto) | S3 |
| Production | 1h | 1h | Hourly (auto) | S3 + Cross-region |

---

## Monitoring

### Backup Success Alerting
```python
# apps/core/tasks.py
@shared_task
def backup_database(output_dir: str, compress: bool = True):
    try:
        # ... backup logic ...
        logger.info("Backup completed", extra={"destination": output_dir})
        
        # Alert on success (optional)
        if settings.BACKUP_ALERT_WEBHOOK:
            requests.post(settings.BACKUP_ALERT_WEBHOOK, json={
                "status": "success",
                "destination": output_dir,
                "timestamp": timezone.now().isoformat()
            })
    except Exception as e:
        logger.exception("Backup failed")
        
        # Alert on failure
        if settings.BACKUP_ALERT_WEBHOOK:
            requests.post(settings.BACKUP_ALERT_WEBHOOK, json={
                "status": "failed",
                "error": str(e),
                "timestamp": timezone.now().isoformat()
            })
        raise
```

---

## Testing Restore

### CI Restore Test
```yaml
# .github/workflows/backup-restore.yml
name: Backup Restore Test

on:
  schedule:
    - cron: '0 4 * * 0'  # Weekly on Sunday

jobs:
  test-restore:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Start services
        run: docker compose up -d db redis minio
      
      - name: Create test data
        run: |
          docker compose run --rm api python manage.py shell -c "
          from apps.accounts.models import User
          User.objects.create_user(email='test@example.com', password='pass')
          "
      
      - name: Backup
        run: |
          docker compose run --rm api python manage.py backup_database \
            --output-dir s3://test-backups/restore-test --compress
      
      - name: Restore to clean DB
        run: |
          docker compose run --rm api python manage.py flush --noinput
          docker compose run --rm api python manage.py restore_database \
            --backup-dir s3://test-backups/restore-test
      
      - name: Verify data
        run: |
          docker compose run --rm api python manage.py shell -c "
          from apps.accounts.models import User
          assert User.objects.filter(email='test@example.com').exists()
          "
```

---

## Disaster Recovery Checklist

- [ ] Backup destination accessible (MinIO/S3)
- [ ] Backup credentials valid
- [ ] Restore procedure documented and tested
- [ ] RPO/RTO targets defined per environment
- [ ] Cross-region replication enabled (production)
- [ ] Alerting on backup failure
- [ ] Restore drill performed quarterly
- [ ] Point-in-time recovery (PITR) for PostgreSQL (if needed)

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| MinIO connection refused | Check `docker compose ps minio`, verify healthcheck |
| S3 access denied | Verify IAM policy, check AWS credentials |
| Backup too slow | Enable compression, use multipart upload |
| Restore fails | Check PostgreSQL version compatibility, verify backup integrity |
| Out of disk space | Clean old backups, enable lifecycle policy |