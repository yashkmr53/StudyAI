# Backup and Recovery — after Phase 8

## Implemented now

- `manage.py backup_database [--output-dir] [--format plain|custom]` — real pg_dump to a timestamped file.
- `manage.py verify_backup --backup-file F [--target-db NAME]` — restores into a scratch database and runs a row-count smoke query; refuses live-DB targets.

## Drill performed (2026-08-21)

Dump of live dev DB written (159,790 bytes), restored into `studyai_restore_verify`, smoke query matched live counts (documents=5, users=4). Scratch DB dropped afterwards.

## Still missing before production

- Scheduled automation (cron/systemd timer or managed snapshots).
- Offsite copy + retention policy.
- Object-store directory backup.
- Documented RPO/RTO targets.
