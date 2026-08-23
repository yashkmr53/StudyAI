# Phase 11 — System Flows

**Date:** 2026-08-23

---

## Provider Selection Flow

```
Application Startup
       │
       ▼
┌──────────────────┐
│ providers/registry│
│   .get_*()       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Read env vars    │
│ STORAGE_BACKEND  │
│ OCR_PROVIDER_    │
│   PROVIDER_CHAIN │
│ LLM_PROVIDER_    │
│   PROVIDER_CHAIN │
│ EMBEDDING_       │
│   PROVIDER       │
│ EMAIL_BACKEND    │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Build Provider Instances            │
│                                     │
│ Storage: LocalObjectStorage()       │
│        or MinIOStorageProvider()    │
│        or S3StorageProvider()       │
│                                     │
│ OCR: OCRChainProvider([...])        │
│    _build_ocr("tesseract")          │
│    _build_ocr("mock")               │
│                                     │
│ LLM: LLMChainProvider([...])        │
│    _build_llm("ollama")             │
│    _build_llm("mock")               │
│                                     │
│ Embed: SentenceTransformerEmbedding │
│        or HashingEmbeddingProvider  │
│                                     │
│ Email: MailpitEmailProvider()       │
│        or SMTPEmailProvider()       │
└─────────────────────────────────────┘
```

---

## OCR Recognition Flow

```
User Uploads Image
       │
       ▼
┌─────────────────────────────┐
│ Ingestion Pipeline          │
│ (apps/ingestion/services)   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_ocr_provider()          │
│ → OCRChainProvider          │
└──────────────┬──────────────┘
               │
               ▼
    ┌──────────┴──────────┐
    │ Primary: Tesseract  │
    │ recognize(uri, req) │
    └──────────┬──────────┘
               │
        ┌──────┴──────┐
        │ Success?    │
        └──────┬──────┘
     Yes /      \ No
      │          │
      ▼          ▼
┌─────────┐ ┌──────────────┐
│ Return  │ │ Log failure  │
│ OCRRes  │ │ Try fallback │
│ provider│ │ (Mock)       │
└─────────┘ └──────┬───────┘
                   │
              ┌────┴────┐
              │ Success?│
              └────┬────┘
           Yes /    \ No
            │        │
            ▼        ▼
      ┌─────────┐ ┌──────────────────┐
      │ Return  │ │ Raise Provider   │
      │ OCRRes  │ │ Error (502)      │
      └─────────┘ └──────────────────┘
```

---

## LLM Generation Flow

```
Enrichment/Chat/Question Pipeline
       │
       ▼
┌─────────────────────────────┐
│ Build Prompt                │
│ - system prompt             │
│ - user prompt + EVIDENCE_JSON│
│ - schema (Pydantic model)   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_llm_provider()          │
│ → LLMChainProvider          │
└──────────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────────────┐
    │ For each provider in chain:     │
    │                                 │
    │ 1. Prepend prompt-injection     │
    │    directive to system prompt   │
    │                                 │
    │ 2. Sanitize user prompt (D5)    │
    │    - Email → [EMAIL]            │
    │    - Phone → [PHONE]            │
    │    - Credit Card → [CREDIT_CARD]│
    │    - SSN → [SSN]                │
    │    - Truncate to MAX_CHARS      │
    │                                 │
    │ 3. Call provider.generate_      │
    │    structured(prompt, schema)   │
    │                                 │
    │ 4. On success:                  │
    │    - Log to ProviderCallLog     │
    │      (tokens, latency, redactions)│
    │    - Return StructuredLLMResult │
    │                                 │
    │ 5. On failure:                  │
    │    - Log failure                │
    │    - Try next provider          │
    │                                 │
    │ 6. If all fail:                 │
    │    - Raise ProviderError (502)  │
    └─────────────────────────────────┘
```

---

## Embedding Generation Flow

```
Document/Note Processing
       │
       ▼
┌─────────────────────────────┐
│ Chunker splits text         │
│ into ~120 word chunks       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_embedding_provider()    │
│ → SentenceTransformer       │
│   EmbeddingProvider         │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ embed(texts, model_version) │
│                             │
│ 1. Check model_version      │
│    matches provider version │
│    (warn if mismatch)       │
│                             │
│ 2. Batch encode with        │
│    normalize_embeddings=True│
│                             │
│ 3. Return list[list[float]] │
│    384-dim, L2 normalized   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Store in pgvector           │
│ NoteChunk.embedding         │
│ (vector(384))               │
└─────────────────────────────┘
```

---

## Object Storage Flow

### Upload
```
Frontend
    │
    ▼
┌─────────────────────────────┐
│ GET /api/v1/storage/        │
│   upload-url?key=...        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_object_storage()        │
│ → MinIOStorageProvider      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ create_upload_url()         │
│ → boto3 generate_presigned_ │
│   _url('put_object', ...)   │
│ → Returns signed URL        │
└──────────────┬──────────────┘
               │
               ▼
    Frontend PUTs directly to MinIO
    (bypasses backend)
```

### Download
```
Frontend
    │
    ▼
┌─────────────────────────────┐
│ GET /api/v1/storage/        │
│   download-url?key=...      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_object_storage()        │
│ → MinIOStorageProvider      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ create_download_url()       │
│ → boto3 generate_presigned_ │
│   _url('get_object', ...)   │
│ → Returns signed URL        │
└──────────────┬──────────────┘
               │
               ▼
    Frontend GETs directly from MinIO
```

---

## Email Flow (Password Reset)

```
User clicks "Forgot Password"
       │
       ▼
┌─────────────────────────────┐
│ POST /api/v1/auth/          │
│   password-reset/           │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Generate reset token        │
│ Build reset URL             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ get_email_provider()        │
│ → MailpitEmailProvider      │
│    (dev) or SMTPEmailProvider│
│    (prod)                   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ send_password_reset_email() │
│                             │
│ Dev: SMTP to mailpit:1025   │
│    → View at http://localhost│
│      :8025                  │
│                             │
│ Prod: SMTP to SendGrid/etc  │
│    → Delivered to user      │
└─────────────────────────────┘
```

---

## Docker Compose Service Dependencies

```
┌─────────────┐
│    db       │◄────────────────┐
│ (pgvector)  │                 │
└─────────────┘                 │
       ▲                        │
       │                        │
       │                        │
┌──────┴──────┐           ┌────┴────┐
│   redis     │           │  minio  │
│  (cache/    │           │ (S3 API)│
│   broker)   │           └─────────┘
└─────────────┘                 ▲
       ▲                        │
       │                        │
       │              ┌────────┴────────┐
       │              │    mailpit      │
       │              │  (SMTP + Web)   │
       │              └─────────────────┘
       │                        ▲
       │                        │
┌──────┴──────┐           ┌────┴────┐
│   ollama    │           │         │
│  (LLM API)  │           │         │
└─────────────┘           │         │
       ▲                  │         │
       │                  │         │
┌──────┴──────────────────┴─────────┴─────┐
│              api / worker / beat        │
│  (depends on: db, redis, minio,         │
│   mailpit, ollama)                      │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  frontend   │
│   (nginx)   │
└─────────────┘
```

---

## Error Handling Flow

```
Provider Call
       │
       ▼
┌─────────────────────────────┐
│ Try Primary Provider        │
└──────────────┬──────────────┘
               │
        ┌──────┴──────┐
        │ Success?    │
        └──────┬──────┘
     Yes /      \ No
      │          │
      ▼          ▼
┌─────────┐ ┌──────────────────┐
│ Log to  │ │ Try Next Provider│
│ Provider│ │ (from chain)     │
│ CallLog │ └────────┬─────────┘
│ (success)│          │
└─────────┘      ┌────┴────┐
                 │Success? │
                 └────┬────┘
              Yes /   \ No
               │       │
               ▼       ▼
        ┌─────────┐ ┌──────────────────┐
        │ Return  │ │ All exhausted?   │
        │ Result  │ └────────┬─────────┘
        └─────────┘      Yes/  \No
                        │       │
                        ▼       ▼
                 ┌──────────┐  (loop)
                 │ Raise    │
                 │ Provider │
                 │ Error    │
                 │ (502)    │
                 └──────────┘
```

---

## Configuration Validation Flow

```
Application Start
       │
       ▼
┌─────────────────────────────┐
│ providers/registry.py       │
│ get_*() called              │
└──────────────┬──────────────┘
               │
               ▼
    ┌──────────┴──────────┐
    │ Production Provider?│
    └──────────┬──────────┘
         Yes /   \ No
          │       │
          ▼       ▼
┌─────────────────┐ ┌──────────────────┐
│ Validate        │ │ Instantiate      │
│ Required Creds  │ │ Local Provider   │
│                 │ │ (no creds needed)│
│ OPENAI_API_KEY  │ │                  │
│ S3_ACCESS_KEY   │ │ Tesseract: check │
│ S3_SECRET_KEY   │ │   tesserocr      │
│ SMTP_HOST       │ │ Ollama: check    │
│                 │ │   /api/tags      │
└────────┬────────┘ │ Embeddings: load │
         │          │   sentence-trans │
    ┌────┴────┐     └──────────────────┘
    │ Valid?  │
    └────┬────┘
  Yes /   \ No
   │       │
   ▼       ▼
┌───────┐ ┌────────────────────────┐
│ Ready │ │ Raise ValueError       │
│       │ │ "X provider requires   │
│       │ │  Y environment var"    │
└───────┘ └────────────────────────┘
```