# Phase 11 — Environment and Secrets

**Date:** 2026-08-23

---

## Environment Variable Reference

### Core Django (Required)
```bash
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_SESSION_COOKIE_SECURE=0
DJANGO_CSRF_COOKIE_SECURE=0
DJANGO_HSTS_SECONDS=0
```

### Database (Required)
```bash
POSTGRES_DB=studyai
POSTGRES_USER=studyai
POSTGRES_PASSWORD=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_SSLMODE=disable
```

### Redis / Celery
```bash
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_BEAT_ENABLED=true
REDIS_THROTTLE_URL=redis://redis:6379/2
```

---

## Phase 11 Provider Variables

### Object Storage
```bash
# Local development (MinIO)
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai
MINIO_REGION=us-east-1
MINIO_SECURE=false

# Production (AWS S3)
# STORAGE_BACKEND=s3
# S3_BUCKET=studyai-prod
# S3_REGION=us-east-1
# S3_ACCESS_KEY=<aws-access-key>
# S3_SECRET_KEY=<aws-secret-key>
# S3_SECURE=true

# Legacy local filesystem
OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_DIR=var/objectstore
SIGNED_URL_TTL_SECONDS=300
```

### OCR
```bash
# Local development
OCR_PROVIDER_CHAIN=tesseract,mock
# Options: mock, tesseract, paddleocr

# Production
# OCR_PROVIDER_CHAIN=google,mock
# OCR_API_KEY=<google-cloud-vision-key>
```

### LLM
```bash
# Local development
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b
# Options: mock, ollama, ollama-chat

# Production
# LLM_PROVIDER_CHAIN=openai,mock
# OPENAI_API_KEY=<openai-key>
# LLM_MODEL=gpt-4o-mini
```

### Embeddings
```bash
# Local development
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto  # cpu, cuda, mps, auto

# Production
# EMBEDDING_PROVIDER=openai
# OPENAI_API_KEY=<openai-key>
# EMBEDDING_MODEL_NAME=text-embedding-3-small
```

### Email
```bash
# Local development (Mailpit)
EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local

# Production (SMTP)
# EMAIL_BACKEND=smtp
# SMTP_HOST=smtp.sendgrid.net
# SMTP_PORT=587
# SMTP_USERNAME=apikey
# SMTP_PASSWORD=<sendgrid-api-key>
# SMTP_USE_TLS=true
# SMTP_USE_SSL=false
# EMAIL_FROM=noreply@studyai.com

# Testing
# EMAIL_BACKEND=console
```

---

## Security Configuration

### CORS / CSRF
```bash
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### Rate Limiting / Budget
```bash
RATE_LIMITING_ENABLED=true
AI_DAILY_BUDGET_PER_PROFILE=500
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00
```

### Provider Input Limits
```bash
MAX_PROVIDER_INPUT_CHARS=8000
```

### Enrichment Coalescing
```bash
ENRICHMENT_COALESCE_WINDOW_SECONDS=300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15
```

### Observability
```bash
PROMETHEUS_METRICS_ENABLED=false
```

---

## Secret Generation

### Generate All Secrets
```bash
#!/bin/bash
# generate_secrets.sh

echo "=== Django ==="
echo "DJANGO_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")"

echo "=== Database ==="
echo "POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")"

echo "=== Production API Keys (fill in manually) ==="
echo "OPENAI_API_KEY=<your-openai-key>"
echo "S3_ACCESS_KEY=<your-aws-key>"
echo "S3_SECRET_KEY=<your-aws-secret>"
echo "SMTP_PASSWORD=<your-sendgrid-key>"
echo "OCR_API_KEY=<your-google-vision-key>"
```

### Quick Generation (Copy-Paste)
```bash
# Django secret
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"

# Database password
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```

---

## Secret Management

### Development (`.env`)
- Commit `.env.example` (template only)
- **Never commit `.env`** — add to `.gitignore`
- Each developer generates their own secrets
- Use safe defaults for local dev (minioadmin, etc.)

### Production
```bash
# Option 1: Docker Secrets
# docker secret create djano_secret_key /path/to/secret.txt

# Option 2: Environment Variables (CI/CD)
# GitHub Actions: Settings > Secrets > Actions
# GitLab CI: Settings > CI/CD > Variables

# Option 3: External Secret Manager
# AWS Secrets Manager, HashiCorp Vault, etc.
```

### Rotation
```bash
# Rotate DJANGO_SECRET_KEY
# 1. Generate new key
# 2. Update all environments
# 3. Restart services (invalidates existing sessions/tokens)
# 4. Users will need to log in again

# Rotate database password
# 1. Update POSTGRES_PASSWORD in all environments
# 2. Update database user
# 3. Restart services

# Rotate API keys
# 1. Create new key in provider console
# 2. Update environment variable
# 3. Restart services
# 4. Revoke old key
```

---

## Variable Precedence

```
1. Docker Compose `environment:` (highest)
2. `.env` file (loaded by docker-compose)
3. Django `settings/base.py` defaults
4. OS environment variables
5. Hardcoded defaults (lowest)
```

**Note**: Django settings use `_get_env()` which checks `settings.X` first, then `os.environ.get()`.

---

## Validation

### Check Required Variables
```bash
# Validate all required vars set
docker compose run --rm api python -c "
import os
required = [
    'DJANGO_SECRET_KEY', 'POSTGRES_PASSWORD',
    'STORAGE_BACKEND', 'OCR_PROVIDER_CHAIN',
    'LLM_PROVIDER_CHAIN', 'EMBEDDING_PROVIDER', 'EMAIL_BACKEND'
]
for var in required:
    val = os.environ.get(var)
    if not val:
        print(f'MISSING: {var}')
    else:
        print(f'OK: {var}={val[:20]}...' if len(val) > 20 else f'OK: {var}={val}')
"
```

### Production Validation
```bash
# Additional production checks
docker compose run --rm api python -c "
import os
prod_required = {
    'STORAGE_BACKEND': 's3',
    'LLM_PROVIDER_CHAIN': 'openai',
    'EMAIL_BACKEND': 'smtp'
}
for var, expected in prod_required.items():
    val = os.environ.get(var, '')
    if expected in val:
        print(f'OK: {var} configured for production')
    else:
        print(f'WARNING: {var}={val} (expected {expected})')
"
```

---

## .env.example Template

See `.env.example` at repository root for complete template with all variables and placeholder values.

### Key Principles
1. **No real values** in `.env.example`
2. **Comments explain** each variable
3. **Generation commands** provided for secrets
4. **Production sections** clearly marked
5. **Local defaults** work out of the box

---

## Migration from Phase 10

### Changed Variables
| Old | New | Notes |
|-----|-----|-------|
| `OBJECT_STORAGE_BACKEND` | `STORAGE_BACKEND` | Supports `minio`, `s3`, `local` |
| `OCR_PROVIDER_CHAIN=mock,mock` | `tesseract,mock` | Local Tesseract |
| `LLM_PROVIDER_CHAIN=mock,mock` | `ollama,mock` | Local Ollama |
| `EMBEDDING_PROVIDER=hashing` | `sentence_transformers` | Local MiniLM |

### Backward Compatibility
- `OBJECT_STORAGE_BACKEND` still read for legacy `LocalObjectStorage`
- `OCR_PROVIDER_CHAIN` defaults to `mock,mock` if not set
- `LLM_PROVIDER_CHAIN` defaults to `mock,mock` if not set
- `EMBEDDING_PROVIDER` defaults to `hashing` if not set