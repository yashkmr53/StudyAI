# Assumptions and Decisions — Phase 5

Prior decisions remain in force (A/B/C/D-series in [`../phase_4/architecture/ASSUMPTIONS_AND_DECISIONS.md`](../architecture/ASSUMPTIONS_AND_DECISIONS.md)). Phase 5 decisions:

| ID | Decision |
|---|---|
| E-001 | `Document.profile` is nullable; reference-book documents have no owning profile. |
| E-002 | NoteChunk keeps the spec's singular `revision_id` (for the §66 constraint) plus a `revision_ids` JSON list recording every revision contributing to the chunk. |
| E-003 | Indexing operates at document level with hash-diffing: chunks whose content hash persists are kept untouched; superseded ones flip to `stale=true`; only new hashes are embedded. |
| E-004 | Embedding provider: feature hashing (word uni+bigrams, MD5 buckets, sign-hash, L2-normalized, 384 dims) — a genuine local technique, not a neural model. |
| E-005 | RRF constant k=60 and candidate depth 50; both settings-tunable but untuned against evaluation data. |
| E-006 | tsvector populated application-side after chunk insert (SearchVector update), config fixed to `'english'`. |
| E-007 | HNSW index (`vector_cosine_ops`) chosen over IVFFlat for recall without training step. |
| E-008 | Reference ingestion via management command reading a JSON file — the "admin upload" of §15 has no UI by design in v1. |
| E-009 | `POST /api/v1/search` added beyond the §60 blueprint so retrieval is exercisable and reusable by chat/enrichment later. |
| E-010 | SQLite unit runs degrade gracefully: vector column stored as text, dense channel skipped (keyword icontains fallback), tsvector population skipped. |

---

## Details

### E-001/E-002 — Modeling deviations
- **Why:** platform reference content must be visible to all users while user chunks stay isolated; multi-page chunks span several revisions.
- **Consequences:** RLS policy on chunks is `(profile match) OR profile IS NULL`; constraint stays spec-exact.
- **Architecture impact:** recorded as deliberate deviations from §10/§29 letter while preserving their guarantees.

### E-003 — Hash-diff incremental indexing
- **Why:** §10 requires embedding only new/changed chunks; content hashing makes change detection exact.
- **Semantics:** same hash ⇒ keep chunk (and its embedding); missing/superseded ⇒ stale-out + insert + embed new. Stale rows retained for audit (§27).
- **Consequences:** repeated indexing is cheap and safe; embeddings never recomputed unnecessarily.

### E-004 — Hashing embedder
- **Why:** true local neural models need torch (~2 GB) — unjustified infrastructure for foundation phase; hashing embeddings still exercise every retrieval property deterministically.
- **Alternatives:** sentence-transformers/bge-small (planned swap), OpenAI embeddings (violates §2 local mandate).
- **Consequences:** similarity is lexical-grade; semantic paraphrase matching weak until model swap. Provider interface unchanged at swap time.

### E-007 — HNSW
- **Why:** better recall/latency trade-off without IVFFlat's training requirement; pgvector 0.8 supports it natively.

### E-009 — Search endpoint beyond blueprint
- **Why:** §60 lists no search route, yet §14 demands exercisable retrieval; chat (Phase 7) will consume the same service.
