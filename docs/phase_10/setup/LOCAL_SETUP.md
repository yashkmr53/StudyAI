# Local Setup — Phase 10

**Status:** Updated with new dependencies and environment variables

---

## Prerequisites

- Docker & Docker Compose v2
- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ (via Docker)
- Redis 7+ (via Docker)

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo>
cd StudyAI
cp .env.example .env
# Edit .env with your values

# 2. Start services
docker compose up -d

# 3. Verify
curl http://localhost/healthz
curl http://localhost/api/v1/healthz
curl http://localhost/metrics  # Prometheus metrics (if enabled)

# 4. Access
# Frontend: http://localhost
# API Docs: http://localhost/api/docs/
# Status: http://localhost/api/v1/status (staff)
```

---

## Environment Variables (Phase 10 Additions)

Add to `.env`:

```bash
# Scheduler
CELERY_BEAT_ENABLED=true

# CORS / CSRF
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Redis throttle cache (DB 2)
REDIS_THROTTLE_URL=redis://redis:6379/2

# Prometheus metrics
PROMETHEUS_METRICS_ENABLED=false  # Set true for metrics endpoint

# Enrichment coalescing
ENRICHMENT_COALESCE_WINDOW_SECONDS=300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD=0.15

# Provider input limits
MAX_PROVIDER_INPUT_CHARS=8000

# Monthly AI budget defaults
DEFAULT_MONTHLY_TOKEN_BUDGET=100000
DEFAULT_MONTHLY_COST_BUDGET_USD=50.00
```

---

## Dependencies

### Backend
```bash
# requirements.txt additions
django-cors-headers>=4.6
django-redis>=5.4
django-prometheus>=2.3
```

### Frontend
```bash
# package.json additions
"vite-plugin-pwa": "^1.0.3",
"@vitest/coverage-v8": "^3.2.4"  # dev
```

---

## Database Setup

```bash
# Run migrations
docker compose exec backend python manage.py migrate

# Create superuser
docker compose exec backend python manage.py createsuperuser

# Load prompt versions (if needed)
docker compose exec backend python manage.py seed_prompts
```

---

## Service Verification

### Health Checks
```bash
# Liveness
curl http://localhost/healthz
# {"status": "ok"}

# Readiness
curl http://localhost/readyz
# {"status": "ok", "database": true}

# Metrics (if enabled)
curl http://localhost/metrics
# Prometheus format output
```

### API Access
```bash
# Register user
curl -X POST http://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "securepass123"}'

# Login
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "securepass123"}'

# Create notebook (requires auth)
curl -X POST http://localhost/api/v1/notebooks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"profile": "<profile_id>", "title": "Test Notebook"}'
```

### Metrics Endpoint
```bash
# Enable in .env: PROMETHEUS_METRICS_ENABLED=true
curl http://localhost/metrics | head -50
```

---

## Development Workflow

### Backend
```bash
cd backend

# Run tests
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest

# With coverage
coverage run -m pytest && coverage report --fail-under=80

# Generate OpenAPI schema
python manage.py spectacular --file docs/openapi/schema.yml

# Run management commands
python manage.py backup_database --output-dir /tmp/test
python manage.py verify_backup --backup-file /tmp/test/studyai_*.dump
```

### Frontend
```bash
cd frontend

# Dev server
npm run dev

# Build
npm run build

# Type check
npx tsc --noEmit

# Tests
npm test
npm run coverage

# Lint
npx eslint src/
```

---

## Debugging

### Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f beat
docker compose logs -f worker
docker compose logs -f frontend
```

### Database
```bash
# Connect to PostgreSQL
docker compose exec db psql -U studyai -d studyai

# Run query
docker compose exec db psql -U studyai -d studyai -c "SELECT * FROM notebooks_notebook;"
```

### Redis
```bash
# Connect
docker compose exec redis redis-cli

# Check throttle cache (DB 2)
redis-cli -n 2 KEYS "*"
redis-cli -n 2 GET "throttle:..."
```

### Celery
```bash
# Beat schedule
docker compose exec beat celery -A config inspect schedule

# Active tasks
docker compose exec worker celery -A config inspect active

# Registered tasks
docker compose exec worker celery -A config inspect registered
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Beat not starting | Check `docker compose logs beat` for Redis connection |
| CORS errors | Verify `CORS_ALLOWED_ORIGINS` includes frontend origin |
| 429 on AI requests | Check budget limits in admin, or increase defaults |
| SW not registering | Must use HTTPS or localhost; check `sw.js` in build output |
| Metrics 404 | Set `PROMETHEUS_METRICS_ENABLED=true` |

---

## Related Documentation

- `docs/phase_10/setup/ENVIRONMENT_AND_SECRETS.md` — All environment variables
- `docs/phase_10/setup/DEPLOYMENT.md` — Production deployment
- `docs/phase_10/setup/CREDENTIALS_AND_ACCESS.md` — Credential management