# Backup and Recovery

## Status: ❌ Not implemented (unchanged after Phase 2)

No backups of any kind are configured and no restore has been rehearsed. Full exposure table, target design from spec §70, and the checklist to close the gap: [`../phase_1/operations/BACKUP_AND_RECOVERY.md`](../../phase_1/operations/BACKUP_AND_RECOVERY.md).

Phase 2 adds one nuance for the future drill: canvas strokes may exist **only client-side** (offline, unsynced). Any recovery procedure must treat unflushed browser outboxes as unrecoverable by server-side restores — the mitigation is the sync loop itself, not backup tooling.
