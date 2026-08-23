# Phase 11 — Operations: Troubleshooting

**Date:** 2026-08-23

---

## Service Health Checks

### All Services
```bash
docker compose ps
# All should show "healthy" or "running"
```

### Individual Services
```bash
# Database
docker compose exec db pg_isready -U studyai

# Redis
docker compose exec redis redis-cli ping

# MinIO
curl -f http://localhost:9000/minio/health/live

# Mailpit
curl -f http://localhost:8025/

# Ollama
docker compose exec ollama ollama list

# Backend API
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/readyz
```

---

## Common Issues

### 1. Ollama Model Not Found
**Error**: `Model 'llama3.1:8b' not found`

**Resolution**:
```bash
# Pull model
docker compose exec ollama ollama pull llama3.1:8b

# List available models
docker compose exec ollama ollama list

# Use different model
# Update .env: LLM_MODEL=mistral:7b
# Pull: docker compose exec ollama ollama pull mistral:7b
```

### 2. Tesseract OCR Fails
**Error**: `RuntimeError: Tesseract OCR not available`

**Resolution**:
```bash
# Check tesseract installation
docker compose exec api tesseract --version

# Check tesserocr Python binding
docker compose exec api python -c "import tesserocr; print(tesserocr.get_tesseract_version())"

# Check languages
docker compose exec api tesseract --list-langs

# Rebuild backend image if missing
docker compose build --no-cache api
```

### 3. MinIO Connection Issues
**Error**: `Connection refused` or `NoSuchBucket`

**Resolution**:
```bash
# Check MinIO logs
docker compose logs minio

# Check bucket exists
docker compose exec minio mc ls minio/studyai

# Create bucket manually
docker compose exec minio mc mb minio/studyai

# Check credentials
docker compose exec minio mc admin user list minio
```

### 4. Mailpit Not Capturing Emails
**Error**: Emails not visible in UI

**Resolution**:
```bash
# Check Mailpit logs
docker compose logs mailpit

# Verify SMTP connection
docker compose exec api python -c "
import smtplib
with smtplib.SMTP('mailpit', 1025) as s:
    s.sendmail('test@test.com', ['to@test.com'], 'Subject: Test\n\nBody')
print('Sent')
"

# Check Mailpit API
curl http://localhost:8025/api/v1/messages
```

### 5. Embedding Dimension Mismatch
**Error**: `pgvector: expected 384 dimensions, got 768`

**Resolution**:
```bash
# Check current provider
docker compose run --rm api python -c "
from providers.registry import get_embedding_provider, embedding_dimension
p = get_embedding_provider()
print(f'Provider: {type(p).__name__}')
print(f'Dimension: {p.dimension}')
print(f'Config dimension: {embedding_dimension()}')
"

# If model changed, run backfill
docker compose run --rm api python manage.py backfill_embeddings \
  --model-version=sentence-transformers-all-MiniLM-L6-v2-v1
```

### 6. Provider Selection Not Working
**Error**: Wrong provider instantiated

**Resolution**:
```bash
# Check env vars in container
docker compose exec api env | grep -E "(STORAGE|OCR|LLM|EMBEDDING|EMAIL)"

# Check Django settings
docker compose run --rm api python -c "
from django.conf import settings
print('STORAGE_BACKEND:', getattr(settings, 'STORAGE_BACKEND', 'NOT SET'))
print('OCR_PROVIDER_CHAIN:', getattr(settings, 'OCR_PROVIDER_CHAIN', 'NOT SET'))
print('LLM_PROVIDER_CHAIN:', getattr(settings, 'LLM_PROVIDER_CHAIN', 'NOT SET'))
print('EMBEDDING_PROVIDER:', getattr(settings, 'EMBEDDING_PROVIDER', 'NOT SET'))
print('EMAIL_BACKEND:', getattr(settings, 'EMAIL_BACKEND', 'NOT SET'))
"

# Restart containers after .env changes
docker compose restart api worker beat
```

### 7. Database Migration Issues
**Error**: `django.db.migrations.exceptions.InconsistentMigrationHistory`

**Resolution**:
```bash
# Check migration status
docker compose run --rm api python manage.py showmigrations

# Fake problematic migration
docker compose run --rm api python manage.py migrate --fake <app> <migration>

# Or reset (DESTRUCTIVE)
docker compose run --rm api python manage.py migrate <app> zero
docker compose run --rm api python manage.py migrate <app>
```

### 8. Celery Tasks Not Running
**Error**: Tasks stuck in queue

**Resolution**:
```bash
# Check worker logs
docker compose logs worker

# Check beat logs
docker compose logs beat

# Verify Redis connection
docker compose exec redis redis-cli INFO keyspace

# Purge queue
docker compose exec redis redis-cli FLUSHDB

# Restart workers
docker compose restart worker beat
```

### 9. Frontend Build Fails
**Error**: TypeScript errors or missing dependencies

**Resolution**:
```bash
# Reinstall dependencies
docker compose run --rm frontend npm ci

# Check TypeScript
docker compose run --rm frontend npx tsc --noEmit

# Clear Vite cache
docker compose run --rm frontend npx vite --force
```

### 10. Out of Memory / Disk Space
**Error**: `No space left on device` or OOM kills

**Resolution**:
```bash
# Check disk usage
df -h
docker system df

# Clean Docker
docker system prune -a --volumes

# Check container memory
docker stats --no-stream

# Increase Docker Desktop memory (if on Mac/Windows)
```

---

## Log Analysis

### Structured Logs
```bash
# Backend logs with request IDs
docker compose logs api | jq -r '.request_id'

# Filter by provider
docker compose logs api | grep -E "(OCR|LLM|Embedding|Storage|Email)"

# Provider call logs
docker compose run --rm api python -c "
from apps.audit.models import ProviderCallLog
for log in ProviderCallLog.objects.order_by('-created_at')[:10]:
    print(f'{log.provider} | {log.model} | {log.latency_ms}ms | {log.success} | {log.error}')
"
```

### Debug Mode
```bash
# Enable debug logging
docker compose exec api python -c "
import logging
logging.getLogger('providers').setLevel(logging.DEBUG)
"
```

---

## Performance Tuning

### Ollama
```bash
# Use smaller model for speed
LLM_MODEL=llama3.1:8b  # 4.7GB
# LLM_MODEL=llama3.2:3b  # 2.0GB (faster, lower quality)
# LLM_MODEL=phi3:mini    # 2.3GB

# Increase context window if needed
# ollama run llama3.1:8b --num-ctx 8192
```

### Embeddings
```bash
# Use GPU if available
EMBEDDING_DEVICE=cuda  # or mps for Apple Silicon

# Increase batch size for throughput
# (modify provider initialization)
```

### MinIO
```bash
# Use SSD storage for MinIO data volume
# Enable compression in backup scripts
```

---

## Security Checks

### Credential Exposure
```bash
# Verify no credentials in images
docker compose run --rm api env | grep -E "(KEY|SECRET|PASSWORD)" | grep -v "minioadmin"

# Check .gitignore
git check-ignore .env
```

### Network Isolation
```bash
# Verify services not exposed externally
docker compose ps --format "table {{.Names}}\t{{.Ports}}"
# Only frontend:80 should be exposed
```

---

## Emergency Procedures

### Complete Reset
```bash
# Stop everything
docker compose down -v

# Remove all volumes
docker volume prune -f

# Restart fresh
docker compose up -d

# Pull Ollama model
docker compose exec ollama ollama pull llama3.1:8b

# Run migrations
docker compose run --rm api python manage.py migrate
```

### Rollback Provider Changes
```bash
# Revert to Phase 10 mock providers
# In .env:
STORAGE_BACKEND=local
OCR_PROVIDER_CHAIN=mock,mock
LLM_PROVIDER_CHAIN=mock,mock
EMBEDDING_PROVIDER=hashing
EMAIL_BACKEND=console

docker compose restart api worker beat
```