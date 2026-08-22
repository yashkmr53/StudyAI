# Environment & Secrets — Phase 10

**Status:** Extended with new Phase 10 variables

---

## Required Environment Variables

### Core (Existing)
```bash
# Django
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_HSTS_SECONDS=31536000

# Database
POSTGRES_DB=studyai
POSTGRES_USER=studyai
POSTGRES_PASSWORD=<generate: python -c "import secrets; print(secrets.token_urlsafe(32))">
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_SSLMODE=disable

# Redis / Celery
CELERY_BROKER_URL=redis://redis:6379/0
```

### Phase 10 Additions

#### Scheduler
```bash
CELERY_BEAT_ENABLED=true
```

#### CORS / CSRF
```bash
# Comma-separated origins
CORS_ALLOWED_ORIGINS=https://app.example.com,https://staging.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com,https://staging.example.com

# Development
# CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
# CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

#### Redis Throttle Cache
```bash
# Separate DB for rate limiting
REDIS_THROTTLE_URL=redis://redis:6379/2
```

#### Prometheus Metrics
```bash
# Enable /metrics endpoint
PROMETHEUS_METRICS_ENABLED=true
```

#### Enrichment Coalescing
```bash
# Time window for coalescing enrichment requests
ENRICHMENT_COALESCE_WINDOW_SECONDS=300

# Cosine similarity threshold (0-1)
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15
```

#### Provider Input Limits
```bash
# Max characters sent to external providers
MAX_PROVIDER_INPUT_CHARS=8000
```

#### Monthly AI Budget Defaults
```bash
# Per-user defaults (overridable in admin)
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00
```

#### Offsite Backup
```bash
# S3, GCS, or rsync URI
OFFSITE_BACKUP_URI=s3://my-bucket/studyai-backups/
# or: gs://my-bucket/studyai-backups/
# or: rsync://user@backup-host/path/to/backups/

# Local retention
BACKUP_RETENTION_DAYS=30
```

#### External AI Providers (Reserved for Phase 11)
```bash
# OCR provider API key
OCR_API_KEY=<your-ocr-key>

# LLM provider API key
LLM_API_KEY=<your-llm-key>

# Local embedding model path
EMBEDDING_MODEL_PATH=<path-to-local-embedding-model>
```

---

## Secrets Management

### Generation Commands
```bash
# Django secret key
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Database password
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generic secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Docker Compose Secrets (Production)
```yaml
# docker-compose.override.yml
services:
  api:
    secrets:
      - django_secret_key
      - postgres_password
      - redis_password

secrets:
  django_secret_key:
    file: ./secrets/django_secret_key.txt
  postgres_password:
    file: ./secrets/postgres_password.txt
```

---

## Environment-Specific Values

### Development (`.env`)
```bash
DJANGO_DEBUG=1
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_SESSION_COOKIE_SECURE=0
DJANGO_CSRF_COOKIE_SECURE=0
DJANGO_HSTS_SECONDS=0
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
PROMETHEUS_METRICS_ENABLED=false
OFFSITE_BACKUP_URI=  # Empty = no offsite copy
```

### Staging (`.env.staging`)
```bash
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=staging.example.com
CORS_ALLOWED_ORIGINS=https://staging.example.com
CSRF_TRUSTED_ORIGINS=https://staging.example.com
PROMETHEUS_METRICS_ENABLED=true
OFFSITE_BACKUP_URI=s3://staging-backups/studyai/
```

### Production (`.env.prod`)
```bash
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=app.example.com,www.example.com
CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com,https://www.example.com
PROMETHEUS_METRICS_ENABLED=true
OFFSITE_BACKUP_URI=s3://prod-backups/studyai/
# All secrets from secret manager / vault
```

---

## Secret Rotation

### Rotation Schedule
| Secret | Frequency | Method |
|--------|-----------|--------|
| `DJANGO_SECRET_KEY` | Annually | Generate new, update env, restart |
| `POSTGRES_PASSWORD` | Quarterly | Update DB user, update env, restart |
| `CELERY_BROKER_URL` password | Quarterly | Update Redis, update env, restart |
| `OFFSITE_BACKUP_URI` credentials | Quarterly | Update cloud provider, update env |
| API keys (OCR, LLM) | Per vendor policy | Update vendor console, update env |

### Rotation Procedure
1. Generate new secret
2. Update secret store (Vault, AWS Secrets Manager, etc.)
3. Update environment variable
4. Rolling restart: `docker compose up -d --no-deps api worker beat`
5. Verify health checks pass
6. Revoke old secret

---

## Access Control

### Secret Access Matrix
| Role | Django Secret | DB Password | Redis Password | API Keys | Backup Creds |
|------|---------------|-------------|----------------|----------|--------------|
| Platform Engineer | R/W | R/W | R/W | R/W | R/W |
| Backend Developer | R | R | R | R | - |
| Frontend Developer | - | - | - | - | - |
| SRE/On-call | R | R | R | R | R |
| CI/CD Pipeline | R | R | R | R | R |

### CI/CD Secrets
```yaml
# GitHub Actions secrets
DJANGO_SECRET_KEY
POSTGRES_PASSWORD
CELERY_BROKER_URL
OFFSITE_BACKUP_URI (with credentials)
OCR_API_KEY
LLM_API_KEY
```

---

## Audit & Compliance

### Secret Access Logging
- All secret access via Vault/AWS Secrets Manager logged
- Rotation events recorded in AuditLog
- Failed access attempts alerted

### Compliance Checks
- No secrets in code (pre-commit hook: `detect-secrets`)
- No secrets in Docker images (multi-stage builds)
- Environment validation on startup (`required_env_vars`)

---

## Related Documentation

- `docs/phase_10/setup/LOCAL_SETUP.md` — Development setup
- `docs/phase_10/setup/DEPLOYMENT.md` — Production deployment
- `docs/phase_10/setup/CREDENTIALS_AND_ACCESS.md` — Access control