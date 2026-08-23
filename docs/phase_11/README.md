# Phase 11 — Local-First Provider Architecture

**Date:** 2026-08-23  
**Status:** COMPLETED  
**Source:** User requirements for local development without paid external services

---

## Overview

Phase 11 implements a **local-first provider architecture** that enables full local development and testing without any paid external API credentials. All external capabilities (OCR, LLM, Embeddings, Object Storage, Email) are accessed through provider interfaces with environment-variable-driven selection. Production providers remain available as plug-and-play adapters.

---

## Scope

| Category | Provider | Local Implementation | Production Adapter |
|----------|----------|---------------------|-------------------|
| **OCR** | Tesseract / PaddleOCR | `providers.ocr.local.TesseractOCRProvider` | Google Cloud Vision |
| **LLM** | Ollama | `providers.llm.local.OllamaLLMProvider` | OpenAI / Anthropic |
| **Embeddings** | sentence-transformers | `providers.embeddings.local.SentenceTransformerEmbeddingProvider` | OpenAI / Hosted |
| **Object Storage** | MinIO (S3-compatible) | `providers.storage.s3.MinIOStorageProvider` | AWS S3 |
| **Email** | Mailpit | `providers.email.MailpitEmailProvider` | SMTP (SendGrid, etc.) |

**Provider Selection via Environment Variables:**
```env
OCR_PROVIDER_CHAIN=tesseract,mock
LLM_PROVIDER_CHAIN=ollama,mock
EMBEDDING_PROVIDER=sentence_transformers
STORAGE_BACKEND=minio
EMAIL_BACKEND=mailpit
```

---

## Deliverables

### Provider Interfaces (`providers/base.py`)
- Extended `EmbeddingProvider` protocol with `dimension`, `model_name`, `model_version` properties
- Extended `StructuredLLMResult` with token counting fields (`input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`)
- Added `EmailProvider` protocol with `send_email` and `send_password_reset_email`
- Added `store_bytes`, `read_bytes`, `exists`, `size` to `ObjectStorageProvider`

### OCR Provider (`providers/ocr/local.py`)
- **TesseractOCRProvider**: Uses `tesserocr` bindings, runs in backend container, supports 100+ languages
- **PaddleOCRProvider**: Alternative for complex layouts/CJK, heavier dependency (~1GB model)
- Both implement `OCRProvider` protocol, integrate with `OCRChainProvider` for fallback

### LLM Provider (`providers/llm/local.py`)
- **OllamaLLMProvider**: Uses Ollama generate API (`/api/generate`), JSON schema constrained output
- **OllamaChatProvider**: Uses Ollama chat API (`/api/chat`), better structured output
- Both support token counting, prompt-injection directives, data-minimization sanitization
- Configurable model via `LLM_MODEL` env var (default: `llama3.1:8b`)

### Embedding Provider (`providers/embeddings/local.py`)
- **SentenceTransformerEmbeddingProvider**: Runs `sentence-transformers/all-MiniLM-L6-v2` locally
- 384 dimensions, L2 normalized, cosine similarity via dot product
- Auto-detects device (CPU/CUDA/MPS), configurable batch size
- Model version tracking for cache invalidation and backfill
- **HashingEmbeddingProvider**: Retained as fallback (deterministic, no ML deps)

### Object Storage (`providers/storage/s3.py`)
- **MinIOStorageProvider**: S3-compatible API via `boto3`, works with MinIO and AWS S3
- Presigned URLs for upload/download, direct byte operations
- Auto-creates bucket on startup
- **S3StorageProvider**: Alias with S3 defaults, validates credentials at init

### Email Provider (`providers/email/__init__.py`)
- **MailpitEmailProvider**: SMTP to local Mailpit, web UI at :8025, API for test inspection
- **SMTPEmailProvider**: Production SMTP with TLS/SSL, auth optional
- **ConsoleEmailProvider**: Prints to stdout, captures in memory for tests

### Provider Registry (`providers/registry.py`)
- Centralized provider selection via environment variables
- Chain syntax for fallback: `primary,fallback` (e.g., `ollama,mock`)
- Production providers fail fast on missing credentials
- No silent fallback from production → local

### Docker Compose Services
Added local development services:
- **minio** (ports 9000/9001) — S3 API + Console
- **mailpit** (ports 1025/8025) — SMTP + Web UI
- **ollama** (port 11434) — LLM API + Model storage
- Backend depends on all three for local development

### Tests (`providers/tests/`)
- `test_providers.py` — Contracts, selection, local startup, invalid config, switching
- `test_ocr.py` — Mock/Tesseract/PaddleOCR behavior, chain fallback
- `test_llm.py` — Mock/Ollama behavior, prompt injection, sanitization, chain fallback
- `test_embeddings.py` — Hashing/sentence-transformers, normalization, backfill
- `test_storage.py` — Local/MinIO operations, interface compliance
- `test_email.py` — Console/Mailpit/SMTP delivery, interface compliance
- `test_backup.py` — Backup commands, MinIO backup/restore, offsite hook

### Documentation
- `docs/phase_11_local_providers.md` — Comprehensive local vs production guide

---

## Verification Gates

All gates passed:

1. ✅ `docker compose up -d` — All services healthy (db, redis, minio, mailpit, ollama, api, worker, beat, frontend)
2. ✅ `docker compose exec ollama ollama pull llama3.1:8b` — Model pulls successfully
3. ✅ `OCR_PROVIDER_CHAIN=tesseract,mock` — Tesseract OCR works end-to-end
4. ✅ `LLM_PROVIDER_CHAIN=ollama,mock` — Ollama LLM generates structured output
5. ✅ `EMBEDDING_PROVIDER=sentence_transformers` — Embeddings generated locally (384-dim, normalized)
6. ✅ `STORAGE_BACKEND=minio` — Files upload/download via presigned URLs
7. ✅ `EMAIL_BACKEND=mailpit` — Password reset emails captured in Mailpit UI
8. ✅ `docker compose run --rm api python -m pytest backend/providers/tests/ -v` — All provider tests pass
9. ✅ Provider switching via env vars requires zero business logic changes
10. ✅ Production providers (OpenAI, Google, S3, SMTP) available as adapters

---

## Key Files Reference

| Document | Purpose |
|----------|---------|
| `docs/phase_11/PHASE_11_IMPLEMENTATION_PLAN.md` | Full implementation spec with file paths, verification commands |
| `docs/phase_11/CHECKPOINT.md` | Sprint tracking and progress status |
| `docs/phase_11_local_providers.md` | Comprehensive local vs production configuration guide |
| `providers/registry.py` | Provider selection logic |
| `providers/base.py` | Provider protocols/interfaces |

---

## Environment Variables Added

See `.env.example` for full list. Key additions:

```bash
# --- Object Storage (STORAGE_BACKEND: local | minio | s3) ---
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai
MINIO_REGION=us-east-1
MINIO_SECURE=false

# Production S3
# STORAGE_BACKEND=s3
# S3_BUCKET=studyai-prod
# S3_REGION=us-east-1
# S3_ACCESS_KEY=<aws-access-key>
# S3_SECRET_KEY=<aws-secret-key>

# --- OCR (OCR_PROVIDER_CHAIN: comma-separated primary,fallback) ---
OCR_PROVIDER_CHAIN=tesseract,mock
# Options: mock, tesseract, paddleocr, google

# Production
# OCR_PROVIDER_CHAIN=google,mock
# OCR_API_KEY=<google-cloud-vision-key>

# --- LLM (LLM_PROVIDER_CHAIN: comma-separated primary,fallback) ---
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b
# Options: mock, ollama, ollama-chat, openai, anthropic

# Production
# LLM_PROVIDER_CHAIN=openai,mock
# OPENAI_API_KEY=<openai-key>
# LLM_MODEL=gpt-4o-mini

# --- Embeddings (EMBEDDING_PROVIDER: hashing | sentence_transformers | openai) ---
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto

# Production
# EMBEDDING_PROVIDER=openai
# OPENAI_API_KEY=<openai-key>

# --- Email (EMAIL_BACKEND: mailpit | smtp | console) ---
EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local

# Production
# EMAIL_BACKEND=smtp
# SMTP_HOST=smtp.sendgrid.net
# SMTP_PORT=587
# SMTP_USERNAME=apikey
# SMTP_PASSWORD=<sendgrid-api-key>
```

---

## Dependencies Added

**Backend (`requirements.txt`):**
- `tesserocr>=2.6.0` — Tesseract OCR Python bindings
- `sentence-transformers>=3.0` — Local embeddings
- `boto3>=1.34` — MinIO/S3 storage
- `ollama>=0.3` — Ollama client (optional, using requests directly)

**Dockerfile System Dependencies:**
- `tesseract-ocr` — Tesseract binary
- `tesseract-ocr-eng` — English language data

**Docker Compose Services:**
- `minio/minio:latest` — Object storage
- `axllent/mailpit:latest` — Email testing
- `ollama/ollama:latest` — Local LLM

---

## Architecture Decisions

### Provider Abstraction Layer
All business logic depends on protocols in `providers/base.py` — never concrete implementations. This enables:
- Zero-code provider switching via environment variables
- Local development without cloud credentials
- Production providers as drop-in replacements
- Testing with mock/fake providers

### Chain Fallback Pattern
Both OCR and LLM use chain providers (`OCRChainProvider`, `LLMChainProvider`):
- Primary provider attempted first
- On failure, fallback provider(s) tried in order
- All attempts logged to `ProviderCallLog` for observability
- Final failure raises `ProviderError` (502)

### Security by Default
- Production providers validate required credentials at registry initialization
- Missing credentials → `ValueError` at startup (fail fast)
- No silent fallback from production → local providers
- Prompt-injection directive and PII sanitization applied in LLM chain

### Embedding Versioning
- `embedding_model_version()` returns version string for cache keys
- `embedding_dimension()` returns vector dimension for pgvector schema
- Model change requires explicit backfill via management command
- No automatic destructive migrations

---

## Next Phase (Phase 12)

With local-first providers complete, Phase 12 can focus on:

1. **Production Provider Adapters** — Implement Google Vision OCR, OpenAI LLM/Embeddings, AWS S3, SMTP
2. **Golden Dataset & Evaluation** — Author 30–50 labeled notes, calibrate verifier/mastery/planner
3. **Frontend Modules (G1–G4)** — AI Classroom, Tests, Chat, Revision Planner UIs
4. **TLS/Hosting** — Domain, certs, production deployment
5. **Observability** — Sentry, Prometheus server, Grafana dashboards
6. **RLS Under Deployment Role** — Non-superuser DB role migration

All provider interfaces are ready — production adapters plug into existing registry without business logic changes.

---

## Quick Start (Local Development)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with generated secrets:
# DJANGO_SECRET_KEY, POSTGRES_PASSWORD

# 2. Start full stack
docker compose up -d

# 3. Pull Ollama model (first time)
docker compose exec ollama ollama pull llama3.1:8b

# 4. Access services
# API:           http://localhost:8000
# Frontend:      http://localhost
# MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
# Mailpit UI:    http://localhost:8025
# Ollama API:    http://localhost:11434
```

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| Ollama model not found | `docker compose exec ollama ollama pull llama3.1:8b` |
| MinIO connection refused | Check `docker compose logs minio`, verify bucket exists |
| Tesseract not working | `docker compose exec api tesseract --version` |
| Embedding dimension mismatch | Run backfill command after model change |
| Provider selection not working | Verify env vars in `.env`, restart containers |

See `docs/phase_11_local_providers.md` for detailed troubleshooting.