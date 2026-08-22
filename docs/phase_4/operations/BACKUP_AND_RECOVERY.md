# Backup and Recovery

## Status: ❌ Not implemented (unchanged)

See [`../phase_3/operations/BACKUP_AND_RECOVERY.md`](../../phase_3/operations/BACKUP_AND_RECOVERY.md) → [`../phase_1/operations/BACKUP_AND_RECOVERY.md`](../../phase_1/operations/BACKUP_AND_RECOVERY.md).

Phase 4 note for the future drill: PDF artifacts are fully **regenerable** from canonical revisions (`POST /documents/{id}/pdf` re-renders deterministically). Recovery therefore prioritizes PostgreSQL + source images; missing PDF objects self-heal via re-render, which the download view surfaces as a clean 404 until then.
