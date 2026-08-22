# Credentials and Access

External services required to run the system, and where credentials live. **No real credentials appear in this file or the repository.**

| Service | Required? | Purpose | Account needed? | Credential needed? | Where credential comes from | Where configured | How to rotate | How to revoke |
|---|---|---|---|---|---|---|---|---|
| PostgreSQL 18 | ✅ Yes (local dev + all envs) | Durable application state | Local: no (socket auth as OS user). Prod: yes | Dev: none. Prod: `POSTGRES_USER`/`POSTGRES_PASSWORD` | DBA / managed-postgres console | `.env` → `config/settings/prod.py` | `ALTER ROLE … WITH PASSWORD …`; update secret store + env | Drop role / revoke grants |
| Redis | ❌ Not yet (Phase 3) | Celery broker only — never durable state | No | `CELERY_BROKER_URL` (may embed password) | Infra team | `.env` | Rotate Redis password, update URL | Flush + ACL restrict |
| Object storage | 🟡 Local FS today (no credentials). S3-compatible in prod later | Private blobs + signed URLs | Later: cloud account | Later: access keys via env/role | Cloud IAM | `OBJECT_STORAGE_BACKEND`, provider settings | IAM rotation policy | Revoke keys / policy |
| OCR provider | ❌ Not until Phase 3 | Handwriting recognition | Provider account | `OCR_API_KEY` (reserved in `.env.example`) | Provider console | `.env` | Provider dashboard | Revoke key |
| LLM provider | ❌ Not until Phase 6 | Enrichment/questions/chat | Provider account | `LLM_API_KEY` (reserved) | Provider console | `.env` | Provider dashboard | Revoke key |
| Embedding provider | ❌ Not until Phase 5 | Local model planned; path reserved | No (local weights) | `EMBEDDING_MODEL_PATH` (reserved) | Model release | `.env` | Swap model version | n/a |
| Email provider | ❌ Not implemented | Password-reset delivery | ESP account | SMTP/API creds | ESP console | Django email settings (not yet present) | ESP dashboard | Revoke creds |
| Monitoring/error tracking | ❌ Not implemented | Metrics/alerts | Vendor account | DSN/key | Vendor | Not configured | Vendor | Vendor |

## Access control summary (application level)

- The only "credentials" the app issues today are JWT pairs bound to a User row.
- Admin site (`/admin/`) uses Django session auth + `is_staff`/`is_superuser` flags.
- No third-party OAuth, no external API calls are made anywhere in the codebase today.

## Rotation drill (PostgreSQL, production-shaped)

```bash
# 1. create/rotate role password
psql -d studyai -c "ALTER ROLE studyai_app WITH PASSWORD '<new-random>';"
# 2. update secret store + environment
# 3. rolling restart of web/worker processes
```
