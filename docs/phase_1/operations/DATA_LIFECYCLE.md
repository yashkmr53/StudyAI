# Data Lifecycle

Covers data that actually exists today; derived-data stages are marked as future.

## Current data and its lifecycle

| Data | Created by | Stored in | Revised? | Deleted when |
|---|---|---|---|---|
| User | registration | `accounts_user` | profile fields via admin only | manually (dev) — cascades to profiles/subjects |
| Profile | registration or `POST /profiles` | `profiles_profile` | PATCH name | DELETE endpoint or user cascade |
| Subject | `POST /subjects` | `subjects_subject` | PATCH name | profile deletion (CASCADE); no direct DELETE endpoint |
| Refresh tokens | login/register | `token_blacklist_outstandingtoken` | blacklisted on rotation/logout | never purged today (cleanup pending) |
| Job rows | none yet (model ready) | `jobs_job` | status transitions | never purged today |
| Local object files | none yet | `backend/var/objectstore/` | n/a | manual delete (gitignored) |
| Browser state | PWA usage | IndexedDB `studyai` + localStorage | strokes updated in place | logout clears tokens; browser eviction clears IDB |

## "What happens when a user deletes a document?" — n/a

Documents don't exist yet. The designed contract (spec §69) they must follow when built:

- Raw uploads: configurable retention, deletable once a canonical revision exists.
- Canonical revisions: retained for reproducibility; immutable.
- Generated PDFs: immutable per revision.
- AI artifacts (chunks, embeddings, enrichments): regenerable from revisions; deletable/regenerable without touching source.
- Questions: marked stale, **never deleted**; attempts retained forever.
- Mastery data: derived from retained attempts.
- Cached results: evictable.
- Stored files: private storage with lifecycle rules.
- Profile deletion: remove/anonymize all owned resources per final privacy policy; reference books unaffected.

## Backups / recovery

**Not implemented.** See [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).

## Retention summary

```text
Today:  dev database persists until manually reset; token blacklist grows unbounded;
        job table empty; object store empty.
Target: policies above enforced in code + lifecycle rules at the storage layer
        (Phase 8 hardening item).
```
