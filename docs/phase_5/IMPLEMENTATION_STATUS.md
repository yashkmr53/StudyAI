# Implementation Status — Phase 5

Legend: ✅ fully implemented · ⚠️ partial · 🟡 simplified/alternative · 🔧 mocked/stubbed · ❌ not implemented

## Overall implementation status

```text
Overall:            ~45% of full v4.1 scope (Phases 1–5 of 8 complete)
Completed:          Security foundation; canvas/offline; ingestion; NoteSpace;
                    AI Classroom foundation — NoteChunk source layer,
                    revision-aware incremental chunking, local embeddings,
                    pgvector dense + tsvector keyword hybrid retrieval (RRF),
                    READY-gated reference-book ingestion, /search API
Partial:            RLS enforcement (dev superuser bypass), reaper scheduling,
                    local-FS storage serving, embedding provider quality
Mocked/stubbed:     OCR providers (synthetic text), password-reset email,
                    LLM registry
Unimplemented:      Enrichment pipeline, citations/verification, tags/mastery,
                    questions/tests, chatbot, revision planner, evaluation
                    harness, reranking stage, rate limiting, audit logging,
                    metrics/health endpoints, backups, CI, deployment artifacts
Major risks:        Embedding quality is lexical-grade only; OCR text synthetic;
                    no backups; no CI
```

## Phase 5 feature audit

### NoteChunk source layer

| Feature | Architecture requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| NoteChunk model per §10 shape | §10 | ✅ | `apps/retrieval/models.py` | `tests/api/test_retrieval.py` | document/profile/subject/revision linkage, page range, content+hash, embedding+model/version, tsvector, stale flag | Spec's singular revision_id kept for §66 constraint; full set in revision_ids JSON (E-002) |
| §66 unique constraint | unique(revision_id, content_hash, chunk_index) | ✅ | migration `retrieval/0001` | duplicate-free inserts asserted implicitly | — | — |
| Profile scoping incl. platform rows | §14/§15 | ✅ | nullable profile FK: user chunks owned, reference chunks NULL | isolation + reference tests | RLS policy mirrors this rule | — |
| RLS on note_chunks | §3 | ⚠️ | migration `retrieval/0003_enable_rls.py` (owner match OR platform row) | policy present via pg_policies | Same superuser caveat as all phases | Restricted-role behavioral test pending |

### Revision-aware chunking & indexing

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Page-aware chunking with context window | §10 | ✅ | `apps/retrieval/services.py::build_chunks` — greedy word-bounded packing across page-ordered lines, overlap carried into next chunk | `ChunkingTests::test_build_chunks_spans_pages_with_context` | Deterministic pure function | Chunk size fixed by words (no token-count model) |
| Incremental indexing — embed only new/changed chunks | §10 | ✅ | content-hash diff vs existing active chunks; unchanged hashes reused without re-embedding | `test_index_rerun_is_incremental_not_duplicating` | stats report kept/staled/created/embedded | — |
| Invalidation on edits: old chunks stale, new indexed, history retained | §10/§27 | ✅ | stale=true supersede + new chunk insert; stale rows retained | `RevisionAwareInvalidationTests` | Triggered automatically from user-edit revisions and OCR completion | Cross-page chunk invalidation granularity is page-range based |
| Downstream hook: OCR → index job | §47 | ✅ | `run_ocr_job` enqueues `index` job after success | full-pipeline E2E | The Phase 3 extension point is now wired | — |
| Index jobs via durable runtime | §19–20 | ✅ | job_type `index`, key `index:{doc}:{combined-hash}:{chunker}:{model}`; eager/broker dispatch | index tests | Duplicate keys collapse to one job | — |

### Local embeddings

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Local embedding provider (no external API) | §2/§31-31 | 🟡 | `providers/embeddings/hashing.py` — feature hashing of word uni+bigrams, L2-normalized, 384 dims | determinism/dimension/difference tests | Real technique but lexical-grade semantics | Swap-in point for a neural local model documented (F-001) |
| Model/version recorded per chunk | §13-adjacent | ✅ | embedding_model + embedding_version columns populated at embed time | model assertions | — | — |

### Hybrid retrieval

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| Dense channel — pgvector cosine | §32/§14 | ✅ | HNSW index (`vector_cosine_ops`) + `CosineDistance` ORM lookup | dense-channel test (PG run) | SQLite unit runs degrade to keyword-only (documented) | — |
| Keyword channel — PostgreSQL FTS | §33 | ✅ | SearchVectorField + GIN index; SearchRank queries | keyword hit test (PG) | Populated post-insert per chunk | Config fixed to 'english' |
| Reciprocal Rank Fusion | §14 | ✅ | k=60 fusion over per-channel rankings | score composition visible in API payload | Constants configurable | Fusion params not tuned (needs eval data) |
| Scoping: profile/subject/source/status (§14) | enforced in SQL | ✅ | queryset filters + read-time READY gate | profile-isolation + non-ready tests | Chat will reuse the same service | — |
| Optional reranking stage | §14 "optional" | ❌ | — | — | Explicitly optional for v1; not needed yet | Revisit when LLM consumers land |
| Search API extension | beyond §60 blueprint (F-004) | ✅ | `POST /api/v1/search` → evidence list w/ scores/snippets | api tests + E2E | Used to exercise retrieval end-to-end | Not in original blueprint — recorded deviation |

### Reference books

| Feature | Requirement | Status | Implementation | Tests | Notes | Known gaps |
|---|---|---|---|---|---|---|
| ReferenceBook/Chapter models | §15 | ✅ | `apps/references/models.py` | ingestion tests | Book ↔ canonical Document OneToOne; chapter page ranges | — |
| Ingestion through canonical layer → READY | §15 | ✅ | `manage.py ingest_reference_book --file book.json` — creates Document(source=reference), pages per chapter, revisions+lines, then indexes and marks READY | ready + retrievability tests | Idempotent per (title, author); eager mode marks READY inline | No admin UI (command is the admin path) |
| Users cannot modify reference content | §15 | ✅ | no public write endpoints exist; Document querysets are profile-scoped so reference docs never appear in user lists | structural | — | — |
| READY gating in retrieval | §15 | ✅ | join-time exclusion + defensive read-time check | non-ready exclusion test | — | — |

## Carried over

Phases 1–4 audits remain valid ([`../phase_4/IMPLEMENTATION_STATUS.md`](../phase_4/IMPLEMENTATION_STATUS.md)). OCR providers still 🔧 mocks; password reset 🔧.

## Final implementation audit

```text
Total architecture requirements tracked: 87   (was 78 after Phase 4)
Fully implemented:            52
Partially implemented:         3
Simplified/alternative:        6
Mocked/stubbed:                3
Not implemented:              23

Tests passing:   backend 80/80 (PostgreSQL); 77 pass + 3 skip (SQLite)
                 frontend 1/1 vitest; production build green
Tests failing:   0
Tests skipped:   3 under SQLite settings only (2 RLS tests + 1 dense-channel test)
Coverage:        not measured
Known security issues:    RLS bypassed by superuser dev role; no rate limiting;
                          tokens in localStorage; password reset stub
Known operational issues: no backups, no health endpoints, no CI, reaper
                          unscheduled, local-FS storage only
Known AI-quality issues:  OCR synthetic (mock); embeddings lexical-grade
                          (hashing); RRF constants untuned; no eval dataset
Known architectural deviations: revision_ids list on chunks (E-002),
                          hashing embedder instead of neural model (F-001),
                          /search endpoint added beyond blueprint (F-004),
                          nullable Document.profile for reference sources (E-001)
```
