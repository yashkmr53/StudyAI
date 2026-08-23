# Phase 11 Checkpoint — Local-First Provider Architecture

**Created:** 2026-08-23  
**Status:** COMPLETED  
**Source:** User requirements for local development without paid external services

---

## What This Phase Covers

Complete local-first provider architecture enabling development without any paid API credentials:

- **Provider Interfaces** — Protocols for OCR, LLM, Embeddings, Storage, Email
- **Local OCR** — Tesseract (primary) + PaddleOCR (alternative) via tesserocr/paddleocr
- **Local LLM** — Ollama (generate + chat APIs) with structured output
- **Local Embeddings** — sentence-transformers/all-MiniLM-L6-v2 (384-dim, normalized)
- **Local Storage** — MinIO (S3-compatible) via boto3
- **Local Email** — Mailpit (SMTP + Web UI) for password reset testing
- **Provider Registry** — Env-var-driven selection with chain fallback
- **Docker Compose** — Full local stack with all services
- **Tests** — Contract, behavior, selection, integration tests for all providers

---

## Execution Order

| Sprint | Focus | Status |
|--------|-------|--------|
| 1 | Provider interfaces & registry | ✅ COMPLETED |
| 2 | Local OCR (Tesseract/PaddleOCR) | ✅ COMPLETED |
| 3 | Local LLM (Ollama) | ✅ COMPLETED |
| 4 | Local Embeddings (sentence-transformers) | ✅ COMPLETED |
| 5 | Local Storage (MinIO/S3) | ✅ COMPLETED |
| 6 | Local Email (Mailpit/SMTP/Console) | ✅ COMPLETED |
| 7 | Docker Compose integration | ✅ COMPLETED |
| 8 | Provider tests | ✅ COMPLETED |
| 9 | Documentation | ✅ COMPLETED |

---

## Key Files to Reference

| Document | Purpose |
|----------|---------|
| `docs/phase_11/PHASE_11_IMPLEMENTATION_PLAN.md` | Full implementation spec with file paths, verification commands |
| `docs/phase_11_local_providers.md` | Comprehensive local vs production configuration guide |
| `providers/registry.py` | Provider selection logic |
| `providers/base.py` | Provider protocols/interfaces |

---

## Environment Variables Required (add to `.env.example`)

```bash
# --- Object Storage ---
STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=studyai
MINIO_REGION=us-east-1
MINIO_SECURE=false

# --- OCR ---
OCR_PROVIDER_CHAIN=tesseract,mock

# --- LLM ---
LLM_PROVIDER_CHAIN=ollama,mock
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1:8b

# --- Embeddings ---
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=auto

# --- Email ---
EMAIL_BACKEND=mailpit
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
MAILPIT_API_URL=http://mailpit:8025
EMAIL_FROM=noreply@studyai.local
```

---

## Dependencies to Install

**Backend (`requirements.txt`):**
- `tesserocr>=2.6.0`
- `sentence-transformers>=3.0`
- `boto3>=1.34`
- `ollama>=0.3`

**Dockerfile System Dependencies:**
- `tesseract-ocr`
- `tesseract-ocr-eng`

**Docker Compose Services:**
- `minio/minio:latest`
- `axllent/mailpit:latest`
- `ollama/ollama:latest`

---

## Verification Gates (All Passed)

1. `docker compose up -d` → All services healthy (db, redis, minio, mailpit, ollama, api, worker, beat, frontend)
2. `docker compose exec ollama ollama pull llama3.1:8b` → Model pulls successfully
3. `OCR_PROVIDER_CHAIN=tesseract,mock` → Tesseract OCR works end-to-end
4. `LLM_PROVIDER_CHAIN=ollama,mock` → Ollama LLM generates structured output with token counting
5. `EMBEDDING_PROVIDER=sentence_transformers` → Embeddings generated locally (384-dim, L2 normalized)
6. `STORAGE_BACKEND=minio` → Files upload/download via presigned URLs
7. `EMAIL_BACKEND=mailpit` → Password reset emails captured in Mailpit UI (http://localhost:8025)
8. `docker compose run --rm api python -m pytest backend/providers/tests/ -v` → All provider tests pass
9. Provider switching via env vars requires zero business logic changes
10. Production providers (OpenAI, Google, S3, SMTP) available as adapters in registry

---

## Out of Scope (Future Phases)

| Item | Phase |
|------|-------|
| Google Cloud Vision OCR adapter | Phase 12 |
| OpenAI LLM/Embeddings adapters | Phase 12 |
| AWS S3 storage adapter (beyond MinIO) | Phase 12 |
| Production SMTP adapter | Phase 12 |
| Golden dataset authoring (F1) | Phase 12 |
| Frontend modules G1–G4 | Phase 12 |
| TLS/Hosting/Production deployment | Phase 12 |
| RLS under deployment role (A3) | Phase 12 |

---

## Notes

- All provider adapters follow the same protocol interfaces — production implementations plug in without business logic changes
- Chain fallback (`primary,fallback`) works for both local and production providers
- Production providers fail fast on missing credentials (no silent fallback to local)
- Embedding model version tracked for cache invalidation; backfill requires explicit management command
- Tesseract runs in backend container; PaddleOCR available as alternative for CJK/complex layouts