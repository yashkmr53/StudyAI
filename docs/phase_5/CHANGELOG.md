# Changelog

## [0.6.0] — 2026-08-22 — Phase 5: AI Classroom Foundation

| Field | Detail |
|---|---|
| Change | Implemented Phase 5 of the v4.1 order (§31 items 29–35): NoteChunk source layer, revision-aware incremental chunking, local hashing embeddings, pgvector dense + tsvector keyword hybrid retrieval with RRF, READY-gated reference-book ingestion through the canonical layer, `/search` API |
| Reason | Foundation for all AI Classroom intelligence (Phases 6–7) |
| Files/modules affected | `backend/apps/retrieval/**` (new app: models/services/retrieval/views/migrations incl. pgvector+RLS), `backend/apps/references/**` (new app + management command), `backend/providers/embeddings/hashing.py`, `backend/providers/registry.py`, `backend/apps/documents/{models,services}.py` (+migrations 0006/0003), `backend/apps/jobs/services.py`, `backend/config/settings/base.py`, `backend/tests/api/test_retrieval.py`, `docs/phase_5/**` |
| Database migration | retrieval 0000_pgvector_extension · 0001_initial · 0002_vector_indexes · 0003_enable_rls · references 0001_initial · documents 0006_alter_document_profile · jobs 0002 (prior) |
| API impact | Added `POST /api/v1/search` (extension beyond §60 blueprint, decision E-009/F-004) |
| Breaking changes | none |

### Backend

- **pgvector**: extension provisioned (Homebrew pgvector 0.8.6), created via guarded migration; NoteChunk.embedding as adaptive vector(384) column; HNSW cosine index.
- **NoteChunk** per spec §10 shape: document/profile/subject/revision linkage, page ranges, content+hash, embedding model/version, tsvector_content, stale flag; §66 triple uniqueness enforced.
- **Chunking**: deterministic page-aware greedy packing with carried context window so page edges don't break concepts.
- **Incremental indexing**: content-hash diff — unchanged chunks never re-embedded; superseded chunks stale-out but retained; only new/changed chunks embedded; stats counters logged.
- **Downstream hook**: OCR success and user-edit revisions now automatically enqueue index jobs (§47 extension point closed).
- **Hybrid retrieval**: dense (CosineDistance) + keyword (SearchRank) channels fused via RRF; profile/subject/stale/READY scoping in SQL plus defensive read-time gating.
- **References**: ReferenceBook/Chapter models; `ingest_reference_book` command ingesting JSON through canonical documents → READY status; users have no write path by design.
- Embedding provider registry entry (`hashing`) + `EMBEDDING_*` settings; SQLite-degradable vector field and tsvector handling.

### Verification

Backend suite: 80 tests — green on PostgreSQL (80/80, incl. dense channel and RLS legs) and SQLite (77 pass + 3 skips). Manual E2E against PostgreSQL: upload → OCR → automatic indexing (embeddings verified) → search hits own notes with RRF scores; reference book ingested to READY and surfaced to a different user while private notes stayed isolated. Frontend build + vitest green.

## [0.5.0] — Phase 4 · earlier
See [`../phase_4/CHANGELOG.md`](../phase_4/CHANGELOG.md).
