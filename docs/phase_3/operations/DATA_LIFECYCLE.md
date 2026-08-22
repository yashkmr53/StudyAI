# Data Lifecycle — after Phase 3

Phase 1/2 lifecycle documentation remains accurate ([`../phase_2/operations/DATA_LIFECYCLE.md`](../../phase_2/operations/DATA_LIFECYCLE.md)). New data classes:

| Data | Created by | Stored | Revised? | Deletion today |
|---|---|---|---|---|
| Documents/pages/revisions/lines | upload finalize / canvas finalize / user edits | PostgreSQL | revisions append-only; never mutated | cascade from profile; no user-facing document delete yet |
| Uploaded/rendered images | storage PUT / rasterizer | `backend/var/objectstore/{profileId}/…` | never overwritten (§47) | manual dev cleanup only |
| OCR jobs | ingestion | `jobs_job` | status transitions | retained (audit) |
| Mock OCR snapshots | worker | revision.content_snapshot | written once per completed run | follows revisions |

## Target policies now concretely applicable

- Raw uploads: currently kept forever alongside the page — configurable retention is a §69 TODO before production.
- Canonical revisions: retained for reproducibility ✅ by construction.
- Generated artifacts (OCR lines/snapshots): regenerable from stored images + job re-run — but with mock providers regeneration reproduces the mock.
- Deleted profiles: CASCADE removes documents; **storage objects are not garbage-collected yet** (orphan risk also exists on transaction rollback after a store_bytes). Cleanup policy = pre-production TODO.

Backups still ❌ — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
