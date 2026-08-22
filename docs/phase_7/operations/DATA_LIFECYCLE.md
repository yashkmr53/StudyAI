# Data Lifecycle — after Phase 7

Prior documentation: [`../phase_6/operations/DATA_LIFECYCLE.md`](../../phase_6/operations/DATA_LIFECYCLE.md). New data classes:

| Data | Created by | Stored | Revised? | Deletion today |
|---|---|---|---|---|
| Tags / DocumentTag links | enrich tail | `ai_classroom_tag` + documenttag | display renames only; identity stable | cascade via subject/document |
| TagChangeLog entries | tagging transitions | append-only | immutable | cascade via tag (snapshot key survives) |
| Questions | enrich tail | `questions_question` | stale flag on source supersession; never deleted | cascade via document |
| Test instances/questions/attempts | POST /tests, attempts | `tests_*` | attempts immutable once written | cascade via profile |
| Mastery scores | attempt grading (EMA) | `tests_masteryscore` | updated per attempt | cascade via profile/tag |
| Chat sessions/messages | chat API | `chat_*` | messages immutable | cascade via profile |
| Revision goals | goals endpoint | `revision_revisiongoal` | none (new goal = new row) | cascade via profile |

## Notes

- Learning history is intentionally permanent: stale questions keep their rows and historical attempts remain linked to them (§17/§27).
- Chat transcripts are user data under profile deletion cascades.
- Backups still ❌ — [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).
