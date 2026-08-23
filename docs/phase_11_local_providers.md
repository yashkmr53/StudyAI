# Phase 11: Local-First Provider Architecture

This document describes the local-first provider architecture implemented in Phase 11, allowing full local development without any paid external services.

## Overview

All external capabilities are accessed through provider interfaces. The provider is selected via environment variables, enabling seamless switching between local and production providers.

```env
# Local development (no API keys required)
OCR_PROVIDER=tesseract
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=sentence_transformers
STORAGE_BACKEND=minio
EMAIL_BACKEND=mailpit

# Production (requires credentials)
OCR_PROVIDER=google
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
STORAGE_BACKEND=s3
EMAIL_BACKEND=smtp
```

## Provider Interfaces

All providers implement protocols defined in `providers/base.py`:

- **OCRProvider**: `recognize(image_uri, request_id) -> OCRResult`
- **LLMProvider**: `generate_structured(prompt, schema, request_id) -> StructuredLLMResult`
- **EmbeddingProvider**: `embed(texts, model_version) -> list[list[float]]`
- **ObjectStorageProvider**: `create_upload_url`, `create_download_url`, `delete`, `store_bytes`, `read_bytes`, `exists`, `size`
- **EmailProvider**: `send_email`, `send_password_reset_email`

Business logic depends only on these protocols, never on concrete implementations.

## Local Providers

### OCR: Tesseract (primary) / PaddleOCR (alternative)

**Tesseract OCR** (`providers.ocr.local.TesseractOCRProvider`):
- Runs inside the backend Docker container
- Uses `tesserocr` Python bindings
- Supports 100+ languages (English included by default)
- Lightweight (~50MB)
- Good for printed text

**PaddleOCR** (`providers.ocr.local.PaddleOCRProvider`):
- Better for complex layouts, tables, handwriting
- Supports CJK languages natively
- Heavier (~1GB model download on first run)
- Optional - install `paddleocr` to enable

Configuration:
```env
OCR_PROVIDER_CHAIN=tesseract,mock  # primary,fallback
# or
OCR_PROVIDER_CHAIN=paddleocr,mock
```

### LLM: Ollama

**Ollama** (`providers.llm.local.OllamaLLMProvider` / `OllamaChatProvider`):
- Runs as separate Docker service (`ollama/ollama`)
- Supports any Ollama-compatible model
- Default: `llama3.1:8b` (4.7GB)
- JSON schema-constrained output
- Token counting for budget tracking

Configuration:
```env
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b
```

To use a different model:
```bash
# Pull model in Ollama container
docker exec -it studyai-ollama-1 ollama pull llama3.1:70b
# Update .env
LLM_MODEL=llama3.1:70b
```

### Embeddings: sentence-transformers

**sentence-transformers** (`providers.embeddings.local.SentenceTransformerEmbeddingProvider`):
- Runs inside backend container
- Default model: `sentence-transformers/all-MiniLM-L6-v2`
- 384 dimensions, L2 normalized
- Cosine similarity = dot product
- CPU/GPU/MPS auto-detection

Model properties:
| Property | Value |
|----------|-------|
| Vector dimension | 384 |
| Model name | sentence-transformers/all-MiniLM-L6-v2 |
| Normalization | L2 (unit vectors) |
| Similarity metric | Cosine (dot product) |
| Persistence format | Float32 array (pgvector) |
| Backfill required | Yes, on model change |

Configuration:
```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto  # cpu, cuda, mps, auto
```

**Backfill procedure** (when changing models):
```bash
# 1. Update model name
EMBEDDING_MODEL_NAME=sentence-transformers/all-mpnet-base-v2

# 2. Run backfill management command
python manage.py backfill_embeddings --model-version=new-version

# 3. Update EMBEDDING_MODEL_VERSION in settings
```

### Object Storage: MinIO

**MinIO** (`providers.storage.s3.MinIOStorageProvider`):
- Runs as separate Docker service (`minio/minio`)
- S3-compatible API
- Web console at http://localhost:9001
- Default credentials: `minioadmin` / `minioadmin`

Configuration:
```env
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai
MINIO_REGION=us-east-1
MINIO_SECURE=false
```

**Production S3** (`providers.storage.s3.S3StorageProvider`):
```env
STORAGE_BACKEND=s3
S3_BUCKET=studyai-prod
S3_REGION=us-east-1
S3_ACCESS_KEY=<aws-access-key>
S3_SECRET_KEY=<aws-secret-key>
S3_SECURE=true
```

### Email: Mailpit

**Mailpit** (`providers.email.MailpitEmailProvider`):
- Runs as separate Docker service (`axllent/mailpit`)
- SMTP on port 1025
- Web UI at http://localhost:8025
- Captures all emails for inspection
- No real emails sent

Configuration:
```env
EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local
```

**Production SMTP** (`providers.email.SMTPEmailProvider`):
```env
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<sendgrid-api-key>
SMTP_USE_TLS=true
EMAIL_FROM=noreply@studyai.com
```

**Testing: Console** (`providers.email.ConsoleEmailProvider`):
```env
EMAIL_BACKEND=console
```

## Docker Compose Services

The local stack includes:

```yaml
services:
  db:           # pgvector/pgvector:pg16
  redis:        # redis:7-alpine
  minio:        # minio/minio (ports 9000, 9001)
  mailpit:      # axllent/mailpit (ports 1025, 8025)
  ollama:       # ollama/ollama (port 11434)
  api:          # Backend API
  worker:       # Celery worker
  beat:         # Celery beat scheduler
  frontend:     # Frontend (nginx + Vite)
```

Volumes:
- `pgdata`: PostgreSQL data
- `objectstore`: Legacy local storage
- `django_static`: Static files
- `minio_data`: MinIO data
- `ollama_data`: Ollama models

## Starting Local Development

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Generate secrets
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"

# 3. Start services
docker compose up -d

# 4. Pull Ollama model (first time only)
docker compose exec ollama ollama pull llama3.1:8b

# 5. Access services
# API: http://localhost:8000
# Frontend: http://localhost
# MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
# Mailpit UI: http://localhost:8025
# Ollama API: http://localhost:11434
```

## Provider Selection

Providers are selected in `providers/registry.py` via environment variables:

| Capability | Env Variable | Local Value | Production Value |
|------------|--------------|-------------|------------------|
| OCR | `OCR_PROVIDER_CHAIN` | `tesseract,mock` | `google,mock` |
| LLM | `LLM_PROVIDER_CHAIN` | `ollama,mock` | `openai,mock` |
| Embeddings | `EMBEDDING_PROVIDER` | `sentence_transformers` | `openai` |
| Storage | `STORAGE_BACKEND` | `minio` | `s3` |
| Email | `EMAIL_BACKEND` | `mailpit` | `smtp` |

The chain syntax (e.g., `ollama,mock`) enables fallback: primary provider attempted first, then fallback(s) on failure.

## Security

- **No credentials in source control**: All secrets via `.env` (gitignored)
- **Production fails fast**: Missing required credentials raise `ValueError` at startup
- **No silent fallbacks**: Production provider → local provider fallback is explicit, not automatic
- **Credential validation**: Registry validates required env vars for production providers

## Testing

Run provider tests:
```bash
# All provider tests
docker compose run --rm api python -m pytest backend/providers/tests/ -v

# Specific provider tests
docker compose run --rm api python -m pytest backend/providers/tests/test_ocr.py -v
docker compose run --rm api python -m pytest backend/providers/tests/test_llm.py -v
docker compose run --rm api python -m pytest backend/providers/tests/test_embeddings.py -v
docker compose run --rm api python -m pytest backend/providers/tests/test_storage.py -v
docker compose run --rm api python -m pytest backend/providers/tests/test_email.py -v
docker compose run --rm api python -m pytest backend/providers/tests/test_backup.py -v
```

## Adding New Providers

1. Create provider class implementing the protocol in `providers/base.py`
2. Add to appropriate package (`ocr/`, `llm/`, `embeddings/`, `storage/`, `email/`)
3. Export from package `__init__.py`
4. Add builder in `providers/registry.py` with env var selection
5. Add tests in `providers/tests/`
6. Update `.env.example` with new variables
7. Update this documentation

## Troubleshooting

### Ollama model not found
```bash
docker compose exec ollama ollama pull llama3.1:8b
# Check available models
docker compose exec ollama ollama list
```

### MinIO connection refused
```bash
# Check MinIO health
docker compose logs minio
# Ensure bucket exists
docker compose exec minio mc ls minio/studyai
```

### Tesseract not working
```bash
# Check tesseract in container
docker compose exec api tesseract --version
# Check languages
docker compose exec api tesseract --list-langs
```

### Embeddings dimension mismatch
```bash
# Verify model dimension matches database
python -c "
from providers.embeddings.local import SentenceTransformerEmbeddingProvider
p = SentenceTransformerEmbeddingProvider()
print(f'Dimension: {p.dimension}')
print(f'Model: {p.model_name}')
print(f'Version: {p.model_version}')
"
```

## Migration from Phase 10

Phase 10 used:
- `OBJECT_STORAGE_BACKEND=local` (filesystem)
- `OCR_PROVIDER_CHAIN=mock,mock`
- `LLM_PROVIDER_CHAIN=mock,mock`
- `EMBEDDING_PROVIDER=hashing`

Phase 11 changes:
- `STORAGE_BACKEND=minio` (replaces `OBJECT_STORAGE_BACKEND`)
- `OCR_PROVIDER_CHAIN=tesseract,mock`
- `LLM_PROVIDER_CHAIN=ollama,mock`
- `EMBEDDING_PROVIDER=sentence_transformers`

Run migrations after updating `.env`:
```bash
docker compose run --rm api python manage.py migrate
```