# Database Schema — after Phase 6

Delta from Phase 5 ([`../phase_5/backend/DATABASE_SCHEMA.md`](../../phase_5/backend/DATABASE_SCHEMA.md)).

## New tables (`apps/ai_classroom/models.py`)

### `ai_classroom_enrichednote`

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| document_id | uuid FK → documents_document | CASCADE |
| content_hash | varchar(64) | sha256 over {document, current revision ids, prompt versions, model} (F-006) |
| revision_ids | JSONB | source revisions covered (strings) |
| generation_job_id | char(32) FK → jobs_job | SET_NULL |
| provider / model | varchar(64)/varchar(128) | e.g. mock / mock-gpt until real model lands |
| prompt_version | varchar(64) | joined qualified names of all stage prompts used |
| schema_version | varchar(32) | output schema version |
| ai_stale | boolean | set when source revisions change after generation (§21/§27) |
| superseded | boolean | older generations retained, excluded from "active" uniqueness |
| created_at | timestamptz | |

Constraints: `uniq_active_enriched_note_hash UNIQUE(document_id, content_hash) WHERE NOT superseded` — partial unique index; history rows exempt.
Indexes: `(document, created_at)`.

### `ai_classroom_enrichednoteblock`

id uuid PK · enriched_note_id FK CASCADE · block_index ≥ 0 · block_type varchar(32) · title varchar(255) blank · content text · **generation_method** choices llm/rule_based/user_edited/transcribed · source_chunk_ids JSONB · created_at.

### `ai_classroom_citationblock`

id uuid PK · enriched_note_block_id **OneToOne** FK CASCADE · source_refs JSONB (list of `{source_type, chunk_id, document_id, page_number, revision_id, retrieval_score}` per §12) · verification_status choices supported/partially_supported/unsupported/not_verified · verification_score float NULL · verifier_version varchar(64) default "none" · created_at.

### `ai_classroom_promptversion`

id uuid PK · prompt_name varchar(64) · version varchar(16) (**unique together**) · template text · output_schema_version varchar(32) · model varchar(128) · configuration JSONB · is_active bool · created_at. Seeded rows: `enrichment_draft:v1`, `gap_detection:v1`, `gap_filling:v1`.

### `evaluation_evalrun`

id uuid PK · kind varchar(32) (retrieval/citation) · dataset_name varchar(255) · metrics JSONB · case_count int ≥ 0 · created_at.

## RLS added

`ai_classroom_enrichednote` / `...enrichednoteblock` / `...citationblock`: EXISTS chains to the document's profile GUC (fail-closed). Same dev-superuser caveat as all phases.

## Migrations added in Phase 6

```text
ai_classroom 0001_initial · 0002_enable_rls
evaluation  0001_initial
```
