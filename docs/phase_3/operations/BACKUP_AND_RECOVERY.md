# Backup and Recovery

## Status: ❌ Not implemented (unchanged)

No backups, no restore rehearsal, no RPO/RTO. See [`../phase_1/operations/BACKUP_AND_RECOVERY.md`](../../phase_1/operations/BACKUP_AND_RECOVERY.md).

Phase 3 addition for the future drill: recovery now spans **two stores** — PostgreSQL and the object-storage directory. The documented drill ("restore DB → restore object references → restart workers → replay pending jobs") applies verbatim; jobs are replayable because revisions/images are content-addressed by hash, and duplicate OCR work is suppressed by idempotency keys.
