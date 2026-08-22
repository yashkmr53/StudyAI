# Architecture — after Phase 5

Delta documentation: Phases 1–4 architecture remains valid ([`../phase_4/architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md)).

## Module status board

| Module / Layer | Status |
|---|---|
| Security foundation | ✅ |
| Canvas + offline sync | ✅ |
| Shared ingestion | ✅ (OCR 🔧 mock) |
| NoteSpace (Module 1) | ✅ |
| **AI Classroom foundation** | ✅ new (embeddings 🟡 hashing) |
| AI Classroom intelligence (enrich/tags/questions/chat) | ❌ Phases 6–7 |
| Ops hardening | ❌ Phase 8 |

## New backend components (Phase 5)

```text
apps/retrieval/
├── models.py       # NoteChunk: vector(384) + tsvector + stale flag
├── services.py     # build_chunks · index_document · enqueue/run_index_job
├── retrieval.py    # RetrievalService.search — dense+keyword RRF
├── views.py        # POST /api/v1/search
└── migrations/     # 0000 pgvector extension · 0001 table · 0002 HNSW/GIN · 0003 RLS

apps/references/
├── models.py       # ReferenceBook (status machine) + chapters
└── management/commands/ingest_reference_book.py

providers/embeddings/hashing.py   # local embedding provider (E-004)
```

## Data flow now working end-to-end

```text
Upload/Canvas finalize → OCR → lines on immutable revision
      ↓ (downstream job hook — §47)
index job: chunk (page-aware, overlap window) → embed (local) → tsvector
      ↓
POST /search {query} → dense ∥ keyword → RRF → scoped top-k evidence
```

## Invariants honored (new this phase)

| Invariant | How it holds |
|---|---|
| Chunks are source material, never generated prose (§9) | chunks built solely from revision lines |
| Every retrieval respects scope/status (§14) | SQL filters + READY gate + stale filter; tested |
| Redis not required for correctness (§32 #12/#14) | eager + DB-polling executor run the full chain |
| Embedding provenance recorded (§13-adjacent) | model/version columns per chunk |

## Component inventory status

| Area | Status |
|---|---|
| Foundation / canvas / ingestion / NoteSpace | ✅ |
| Retrieval foundation (chunks/embed/index/search) | ✅ (embedding quality 🟡) |
| References corpus | ✅ ingestion path; no admin UI |
| Intelligence (enrich/citations/questions/chat/planner) | ❌ Phase 6–7 |
| Ops hardening | ❌ |
