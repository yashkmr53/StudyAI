# Phase 11 — Local Development Setup

**Date:** 2026-08-23

---

## Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose v2)
- 8GB+ RAM available for containers
- 10GB+ disk space for images, volumes, and Ollama models

---

## Quick Start

### 1. Clone and Configure
```bash
git clone <repo>
cd StudyAI

# Copy environment template
cp .env.example .env

# Generate secrets (run each, copy output to .env)
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```

### 2. Start Services
```bash
# Start all services (first pull takes 5-10 min)
docker compose up -d

# Watch logs
docker compose logs -f

# Wait for all services to be healthy
docker compose ps
```

### 3. Pull Ollama Model (First Time Only)
```bash
# Pull default model (4.7GB)
docker compose exec ollama ollama pull llama3.1:8b

# Or pull alternative
docker compose exec ollama ollama pull mistral:7b
docker compose exec ollama ollama pull phi3:mini
```

### 4. Run Migrations
```bash
docker compose run --rm api python manage.py migrate
```

### 5. Create Superuser (Optional)
```bash
docker compose run --rm api python manage.py createsuperuser
```

### 6. Access Services
| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost | — |
| API | http://localhost:8000 | — |
| API Docs | http://localhost:8000/api/schema/swagger-ui/ | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Mailpit UI | http://localhost:8025 | — |
| Ollama API | http://localhost:11434 | — |

---

## Environment Configuration

### Required Variables (`.env`)
```bash
# Django
DJANGO_SECRET_KEY=<generated>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
POSTGRES_DB=studyai
POSTGRES_USER=studyai
POSTGRES_PASSWORD=<generated>
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Provider Selection (Phase 11 defaults)
STORAGE_BACKEND=minio
OCR_PROVIDER_CHAIN=tesseract,mock
LLM_PROVIDER_CHAIN=ollama,mock
EMBEDDING_PROVIDER=sentence_transformers
EMAIL_BACKEND=mailpit
```

### Optional Overrides
```bash
# Ollama
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b

# Embeddings
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto

# MinIO
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai

# Mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local
```

---

## Verification Steps

### 1. Health Checks
```bash
# All services healthy
docker compose ps

# API responding
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/readyz
```

### 2. Provider Tests
```bash
# Run all provider tests
docker compose run --rm api python -m pytest backend/providers/tests/ -v

# Expected: All tests pass (7 test files, 50+ tests)
```

### 3. Manual Provider Verification
```bash
# OCR
docker compose run --rm api python -c "
from providers.registry import get_ocr_provider
ocr = get_ocr_provider()
print('OCR Provider:', type(ocr).__name__)
"

# LLM
docker compose run --rm api python -c "
from providers.registry import get_llm_provider
llm = get_llm_provider()
print('LLM Provider:', type(llm).__name__)
"

# Embeddings
docker compose run --rm api python -c "
from providers.registry import get_embedding_provider, embedding_dimension
emb = get_embedding_provider()
print('Embedding Provider:', type(emb).__name__)
print('Dimension:', embedding_dimension())
"

# Storage
docker compose run --rm api python -c "
from providers.registry import get_object_storage
storage = get_object_storage()
print('Storage Provider:', type(storage).__name__)
url = storage.create_upload_url('test.txt', 'text/plain', 300)
print('Upload URL:', url[:80] + '...')
"

# Email
docker compose run --rm api python -c "
from providers.registry import get_email_provider
email = get_email_provider()
print('Email Provider:', type(email).__name__)
email.send_password_reset_email(
    to='test@example.com',
    reset_url='http://localhost/reset?token=abc',
    user_name='Test User'
)
print('Email sent')
"
```

### 4. Check Mailpit for Test Email
Open http://localhost:8025 → See captured password reset email

---

## Development Workflow

### Code Changes
```bash
# Backend changes: auto-reload (if using runserver)
# For gunicorn: restart container
docker compose restart api

# Frontend changes: Vite HMR works automatically
# Edit files in frontend/src/
```

### Running Commands
```bash
# Django management commands
docker compose run --rm api python manage.py <command>

# Shell access
docker compose run --rm api python manage.py shell

# Database shell
docker compose run --rm api python manage.py dbshell

# Run tests
docker compose run --rm api python -m pytest <path> -v
```

### Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f ollama
```

---

## Common Tasks

### Pull Different Ollama Model
```bash
docker compose exec ollama ollama pull llama3.1:70b
# Update .env: LLM_MODEL=llama3.1:70b
docker compose restart api worker beat
```

### Change Embedding Model
```bash
# Update .env
EMBEDDING_MODEL_NAME=sentence-transformers/all-mpnet-base-v2

# Restart to reload model
docker compose restart api worker beat

# Run backfill (if needed)
docker compose run --rm api python manage.py backfill_embeddings \
  --model-version=sentence-transformers-all-mpnet-base-v2-v1
```

### Reset Database
```bash
# WARNING: Destructive
docker compose down -v
docker compose up -d
docker compose run --rm api python manage.py migrate
```

### Backup/Restore
```bash
# Backup to MinIO
docker compose run --rm api python manage.py backup_database \
  --output-dir s3://studyai-backups/$(date +%Y-%m-%d) --compress

# Restore
docker compose run --rm api python manage.py restore_database \
  --backup-dir s3://studyai-backups/2024-01-15
```

---

## IDE Configuration

### VS Code
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "/usr/local/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit"
  }
}
```

### Remote Containers (Optional)
```json
// .devcontainer/devcontainer.json
{
  "name": "StudyAI",
  "dockerComposeFile": "../docker-compose.yml",
  "service": "api",
  "workspaceFolder": "/app",
  "extensions": ["ms-python.python", "ms-python.ruff"]
}
```

---

## Troubleshooting Setup

| Issue | Solution |
|-------|----------|
| `docker compose up` hangs | Check `docker compose logs` for specific service |
| Port conflicts (80, 5432, 6379, 9000, 8025, 11434) | Stop conflicting services, or change ports in `docker-compose.yml` |
| Ollama model pull fails | Check disk space, try smaller model (`phi3:mini`) |
| Tesseract not found | Rebuild: `docker compose build --no-cache api` |
| Permission denied on volumes | `sudo chown -R $USER:$USER .` or fix Docker Desktop file sharing |
| Out of memory | Increase Docker Desktop memory limit to 8GB+ |
| Frontend not loading | Check `docker compose logs frontend`, verify nginx config |

---

## Production vs Development

| Setting | Development | Production |
|---------|-------------|------------|
| `DJANGO_DEBUG` | `1` | `0` |
| `DJANGO_SECURE_SSL_REDIRECT` | `0` | `1` |
| `STORAGE_BACKEND` | `minio` | `s3` |
| `OCR_PROVIDER_CHAIN` | `tesseract,mock` | `google,mock` |
| `LLM_PROVIDER_CHAIN` | `ollama,mock` | `openai,mock` |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | `openai` or `sentence_transformers` |
| `EMAIL_BACKEND` | `mailpit` | `smtp` |

See `.env.example` for production template.