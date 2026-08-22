# Data Lifecycle — after Phase 4

Prior lifecycle documentation: [`../phase_3/operations/DATA_LIFECYCLE.md`](../../phase_3/operations/DATA_LIFECYCLE.md). New data class:

| Data | Created by | Stored | Immutable? | Deletion today |
|---|---|---|---|---|
| DigitizedDocument rows + PDF objects | pdf_render job | `documents_digitizeddocument` + object storage | ✅ never mutated; superseded artifacts retained | cascade from profile/document; no GC |

## §69 targets now concretely satisfied

- "Generated PDFs: immutable per source revision" — ✅ by content-addressing; edits yield new artifacts, old ones retained.
- "AI artifacts can be regenerated from source revisions" — PDFs re-render deterministically from revisions + renderer version.

## Open gaps

- Superseded artifact GC (retention policy TBD, spec §30).
- Uploaded image retention still unbounded.
- Profile deletion cascades rows but not yet storage objects.

Backups still ❌ — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
