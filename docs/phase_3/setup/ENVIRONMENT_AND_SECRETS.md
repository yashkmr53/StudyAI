# Environment and Secrets — after Phase 3

Base reference: [`../phase_2/setup/ENVIRONMENT_AND_SECRETS.md`](../setup/ENVIRONMENT_AND_SECRETS.md) → [`../phase_1/setup/ENVIRONMENT_AND_SECRETS.md`](../../phase_1/setup/ENVIRONMENT_AND_SECRETS.md). New variables:

| Variable | Required? | Purpose | Default | Used by | Rotation |
|---|---|---|---|---|---|
| `OCR_PIPELINE_VERSION` | No | OCR idempotency key component (§20) | `mock-v1` | `apps/documents/services.py` | Bump to force re-OCR of unchanged content |
| `OCR_PROVIDER_CHAIN` | No | Primary/fallback provider names | `["mock","mock"]` | `providers/registry.py` | n/a |
| `OCR_REVIEW_THRESHOLD` | No | Avg confidence below → needs_review | `0.80` | `run_ocr_job` | Calibrate per §26 |
| `UPLOAD_MAX_BYTES` | No | Upload size cap | `10485760` | storage upload view | n/a |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | No | Type allow-list | jpeg/png/webp | storage upload view | n/a |
| `JOBS_MAX_ATTEMPTS` | No | Attempts before dead-letter | `3` | executor | n/a |
| `JOBS_RETRY_BASE_SECONDS` / `_CAP_SECONDS` | No | Backoff curve | 5 / 300 | `retry_backoff` | n/a |
| `JOBS_TIMEOUT_SECONDS` | No | Reaper threshold for RUNNING jobs | `600` | `reap_stuck_jobs` | n/a |

Secret rules unchanged: no committed credentials (scan clean), `.env` gitignored, prod requires explicit secret key. No external provider keys exist yet — placeholders reserved in `.env.example`.
