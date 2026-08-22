# Environment and Secrets — after Phase 8

Delta from [`../phase_7/setup/ENVIRONMENT_AND_SECRETS.md`](../../phase_7/setup/ENVIRONMENT_AND_SECRETS.md):

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `RATE_LIMITING_ENABLED` | No | Master gate for throttling | `True` (base); `False` in dev/test settings | shared/throttles.py | n/a |
| `UPLOAD_SNIFF_MAGIC_BYTES` | No | Magic-byte content validation on uploads | `True` | storage upload view | n/a |
| `AI_DAILY_BUDGET_PER_PROFILE` | No | Max enrich jobs + assistant chat messages per profile/day; unset disables | `500` | budget.py → enrich/chat 429s | n/a |

All prior variables unchanged. Secret scan remains clean — no provider keys exist in the repository.
