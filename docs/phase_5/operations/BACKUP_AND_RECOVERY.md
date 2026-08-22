# Backup and Recovery

## Status: ❌ Not implemented (unchanged)

See [`../phase_4/operations/BACKUP_AND_RECOVERY.md`](../../phase_4/operations/BACKUP_AND_RECOVERY.md) → [`../phase_1/…`](../../phase_1/operations/BACKUP_AND_RECOVERY.md).

Phase 5 note: chunks/embeddings are **derived data** — fully recoverable by re-running index jobs after a database restore (source revisions are the inputs). This keeps the recovery drill unchanged: restore DB → restore objects → replay jobs.
