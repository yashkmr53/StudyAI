# Data Lifecycle — after Phase 6

Prior documentation: [`../phase_5/operations/DATA_LIFECYCLE.md`](../../phase_5/operations/DATA_LIFECYCLE.md). New data class:

| Data | Created by | Stored | Revised? | Deletion today |
|---|---|---|---|---|
| EnrichedNote generations | enrich / refresh-ai jobs | `ai_classroom_enrichednote` (+blocks/citations) | new generation supersedes; old rows retained with `superseded=true` | cascade from document/profile |
| PromptVersion registry rows | seed + future bumps | `ai_classroom_promptversion` | versioned append-only; old versions kept active=false | never (audit) |
| EvalRun records | `run_ai_evaluation` | `evaluation_evalrun` | immutable metrics snapshot | manual |

## §27 propagation now partially live

Source revision change → index job → **EnrichedNote.ai_stale = true** (automatic). Regeneration via refresh-ai produces a new generation bound to the new revisions; the stale-flagged generation remains for audit until a GC policy exists.

## Notes

- Enrichment content is derived from 🔧 mock OCR — regenerable, but reproducing synthetic text.
- PromptVersion history is intentional audit data.
- Backups still ❌ — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
