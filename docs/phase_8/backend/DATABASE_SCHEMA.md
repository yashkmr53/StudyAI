# Database Schema — after Phase 8

Delta from Phase 7 ([`../phase_7/backend/DATABASE_SCHEMA.md`](../../phase_7/backend/DATABASE_SCHEMA.md)).

## New tables (`apps/audit/models.py`)

### `audit_auditlog` (§23 administrative audit logging)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| actor_id | char(32) FK → accounts_user, **SET_NULL** + actor_email snapshot | history survives deletion |
| action | varchar(64) | user.registered / user.login / user.logout / document.created / … |
| resource_type / resource_id | varchar(64) | target reference |
| metadata | JSONB | extra context (no secrets/content) |
| ip_address | inet-compatible generic IP nullable | |
| created_at | timestamptz | |

Indexes: `(action, created_at)` · `(actor, created_at)`.

### `audit_providercalllog` (§25 provider usage)

id uuid PK · provider varchar(64) · model varchar(128) · latency_ms int ≥ 0 · success bool · error text (truncated 500) · created_at.
Index: `(provider, success, created_at)`.

## RLS cumulative coverage — 33 tables with policies

Prior bundles plus: none new this phase beyond audit tables being intentionally **without RLS** (staff-only API gate instead; audit rows are platform records, not tenant rows).

Full policy list: profiles/subjects/canvas(3)/documents(4)/retrieval notechunk/questions/tests(3)/chat(2)/revision/ai_classroom(3).

## Migrations added in Phase 8

```text
audit 0001_initial
```

No changes to existing domain tables in Phase 8; the `RATE_LIMITING_ENABLED`, `UPLOAD_SNIFF_MAGIC_BYTES`, and `AI_DAILY_BUDGET_PER_PROFILE` settings are runtime configuration, not schema.
