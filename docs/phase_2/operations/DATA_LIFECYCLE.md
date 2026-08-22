# Data Lifecycle — after Phase 2

Phase 1 lifecycle documentation ([`../phase_1/operations/DATA_LIFECYCLE.md`](../../phase_1/operations/DATA_LIFECYCLE.md)) remains accurate for users/profiles/subjects/tokens/jobs. Phase 2 adds canvas data.

## Canvas data lifecycle (actual)

| Data | Created | Stored | Revised? | Deleted |
|---|---|---|---|---|
| Canvas session | "New sheet" / POST sessions | `canvas_canvassession` | lock state mutates; domain fields don't | profile deletion (CASCADE); no user-facing delete yet |
| Canvas page | "+ Page" / POST pages | `canvas_canvaspage` | `is_finalized` flips once, immutably | session cascade |
| Strokes | drawing | IndexedDB immediately → `canvas_canvasstroke` on sync | never edited after creation | page cascade |
| Outbox ops | each stroke | IndexedDB only | pending → acknowledged | acknowledged rows accumulate locally until browser eviction |

## Deletion semantics to note

- Deleting a **subject** does not delete sheets: `subject_id` is `SET_NULL` (deliberate — canvas work survives subject reorganization).
- Deleting a **profile/user** cascades all canvas data.
- Finalized pages are immutable at the service layer; there is currently no un-finalize path.
- Local-only strokes (captured offline, not yet synced) live only in the browser: clearing site data loses them. Server-side dedupe makes re-flush safe but cannot recreate lost local data.

## Backups

Still ❌ none configured — see [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
