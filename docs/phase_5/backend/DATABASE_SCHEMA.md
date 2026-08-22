# Database Schema — after Phase 5

Delta from Phase 4 ([`../phase_4/backend/DATABASE_SCHEMA.md`](../../phase_4/backend/DATABASE_SCHEMA.md)). Full ER diagram in prior phases remains valid plus the new tables below.

## New tables

### `retrieval_notechunk` — `apps/retrieval/models.py`

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| document_id | uuid FK → documents_document | CASCADE |
| profile_id | uuid FK → profiles_profile, **NULL allowed** | SET_NULL; NULL = platform reference chunk |
| subject_id | uuid FK → subjects_subject | SET_NULL nullable |
| revision_id | uuid | primary revision — §66 constraint member (E-002) |
| revision_ids | JSONB | all contributing revisions |
| page_start / page_end | integer ≥ 0 | chunk page range |
| chunk_index | integer ≥ 0 | §66 constraint member |
| content | text | verbatim lines incl. carried context window |
| content_hash | varchar(64) | sha256 of content; change-detection key |
| source_type | varchar(20) | image / canvas_page / reference |
| reference_book_id | uuid FK → references_referencebook | SET_NULL nullable |
| embedding | **vector(384)** nullable | pgvector column (text on SQLite); HNSW cosine index |
| embedding_model / embedding_version | varchar nullable | e.g. hashing / hashing-384-v1 |
| tsvector_content | tsvector nullable | GIN-indexed keyword search column |
| stale | boolean default false | superseded chunks excluded from retrieval, retained |
| created_at | timestamptz | |

Constraints: `uniq_notechunk_revision_hash_index UNIQUE (revision_id, content_hash, chunk_index)` (§66 exact).
Indexes: `(document_id, stale)` · GIN `(tsvector_content)` · HNSW `(embedding vector_cosine_ops)`.
RLS: enabled — `profile match OR profile IS NULL` policy.

### `references_referencebook` / `references_referencebookchapter` — `apps/references/models.py`

Book: id, subject_id FK SET_NULL, title, author, edition, isbn, **status** (draft/processing/ready/failed), OneToOne `document` → canonical Document, created_at.
Chapter: id, book_id FK CASCADE, chapter_number (**unique per book**), title, page_range_start/end.

No RLS on references tables (platform-curated, read-only to the app tier).

## Modified

- `documents_document.profile_id` now **nullable** — platform reference documents have no owning profile (E-001). Migration `documents/0006_alter_document_profile`.
- `documents_documentline.is_heading` and DigitizedDocument table from Phase 4 unchanged.

## Indexes added

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE INDEX idx_notechunk_hnsw_embedding ON retrieval_notechunk USING hnsw (embedding vector_cosine_ops);
-- GIN via Django GinIndex:
CREATE INDEX idx_notechunk_gin_tsv ON retrieval_notechunk USING gin (tsvector_content);
```

## Migrations added in Phase 5

```text
retrieval  0000_pgvector_extension (run_before 0001)
retrieval  0001_initial · 0002_vector_indexes · 0003_enable_rls
references 0001_initial
documents  0006_alter_document_profile
```

## Deviations from spec schema

1. NoteChunk.revision_ids list alongside singular revision_id (E-002).
2. Nullable profile on Document/NoteChunk for platform reference content (E-001) — spec §29 implies but does not state it.
3. Embedding stored inline per §10 shape (no separate Embedding table) — matches spec §10 exactly.
