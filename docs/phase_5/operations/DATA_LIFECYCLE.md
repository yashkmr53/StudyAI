# Data Lifecycle — after Phase 5

Prior documentation: [`../phase_4/operations/DATA_LIFECYCLE.md`](../../phase_4/operations/DATA_LIFECYCLE.md). New data class:

| Data | Created by | Stored | Revised? | Deletion today |
|---|---|---|---|---|
| NoteChunks + embeddings + tsvector | index jobs / reference ingestion | `retrieval_notechunk` (+ vector/tsvector columns) | superseded → `stale=true`, retained forever | cascade from document/profile; no direct GC |
| Reference books/chapters/pages | management command | `references_*` + canonical Document | re-ingestion skipped for existing title/author | manual only |

## Notes

- Stale chunks are **retained** by design (§27 historical retention) — retrieval excludes them; nothing prunes them yet.
- Embeddings are derived data: fully regenerable from chunk contents; model/version recorded so regeneration can be scoped to a model change.
- Reference books survive user/profile deletion (profile NULL, subject SET_NULL) per §15.
- Vector column size: 384 floats × chunks — modest growth; watch when large corpora land.

Backups still ❌ — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
