# Backup and Recovery

## Status: ❌ Not implemented

No backups of any kind are configured. No restore has ever been rehearsed. This is a Phase 8 exit criterion (spec §77) and a pre-production blocker.

## Current exposure

| Asset | Backup | Loss risk |
|---|---|---|
| PostgreSQL `studyai` (dev) | none | full data loss on disk failure / bad reset |
| `backend/var/objectstore/` | none | empty today, but unprotected |
| Code | Git repository only | acceptable |

## Local dev "recovery" (the only procedure that exists)

```bash
dropdb studyai && createdb studyai
cd backend && ../myenv/bin/python manage.py migrate
# re-register users; object store is disposable
```

## Target design (spec §70 — to implement before production)

```text
PostgreSQL:  daily full backup + point-in-time recovery where supported
Object storage: versioning + lifecycle rules
Redis:       no backup — explicitly not a source of truth

Recovery drill: restore DB → restore object references → restart workers → replay pending jobs
```

### RPO / RTO

**Not defined.** Must be chosen before production; both depend on hosting decisions (spec §30 open item: hosting provider).

### Checklist to close this gap

1. Choose managed Postgres vs self-hosted WAL archiving.
2. Automate daily dumps + retention policy.
3. Enable storage versioning when S3-compatible provider lands.
4. Script the recovery drill; execute and time it.
5. Record achieved RPO/RTO here.
