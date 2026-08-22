# Environment and Secrets — after Phase 2

Unchanged from Phase 1 except one new setting. Full variable reference: [`../phase_1/setup/ENVIRONMENT_AND_SECRETS.md`](../../phase_1/setup/ENVIRONMENT_AND_SECRETS.md).

## New in Phase 2

| Variable | Required? | Purpose | Example | Used by | Rotation |
|---|---|---|---|---|---|
| `CANVAS_LOCK_TTL_SECONDS` | No | Canvas single-writer lease duration (§5); default `90` | `90` | `apps/canvas/services.py` | n/a (operational tuning) |

Template remains `.env.example` at repo root (placeholders only). No new credentials, keys, or external services were introduced by Phase 2. Secret scan: clean.
