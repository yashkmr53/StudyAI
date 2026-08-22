# Data Lifecycle — final additions

Prior lifecycle documentation stands ([../../phase_7/operations/DATA_LIFECYCLE.md](DATA_LIFECYCLE.md)). Phase 8 adds:

- **AuditLog rows**: append-only operational history; no automatic pruning (policy TBD before production).
- **ProviderCallLog rows**: telemetry; prune by age once volume grows (Phase 8+ housekeeping task).

Everything else — documents/revisions immutable, attempts retained, superseded artifacts retained — unchanged. Scheduled backup automation remains absent: see BACKUP_AND_RECOVERY.md.
