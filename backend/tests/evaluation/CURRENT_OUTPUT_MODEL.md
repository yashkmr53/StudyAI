# Current Enrichment Output Model (StudyAI)

## Overview

This document describes the exact enrichment output structure produced by the StudyAI pipeline as of the baseline evaluation phase.

---

## Pipeline Stages

The enrichment graph executes these stages sequentially:

```
retrieve → draft → gap_detection → [gap_fill] → citation_stitch → evidence_verification → format_output
```

---

## 1. EnrichedNote (Top-Level Container)

**Model**: `apps.ai_classroom.models.EnrichedNote`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `document` | FK → Document | Source document |
| `content_hash` | Char(64) | SHA256 of descriptor (document + revisions + prompt versions + model) |
| `revision_ids` | JSON[UUID] | Source revision IDs covered |
| `generation_job` | FK → Job | Job that produced this enrichment |
| `provider` | Char(64) | LLM provider name (e.g., "ollama") |
| `model` | Char(128) | LLM model name (e.g., "qwen2.5:7b") |
| `prompt_version` | Char(64) | Semicolon-separated qualified prompt names (e.g., "enrichment_draft:v1;gap_detection:v1;gap_filling:v1") |
| `schema_version` | Char(32) | Output schema version (e.g., "v1") |
| `ai_stale` | Boolean | True when source revisions have changed |
| `superseded` | Boolean | True for older generations (only one active per document) |
| `created_at` | DateTime | Creation timestamp |

---

## 2. EnrichedNoteBlock (Enrichment Blocks)

**Model**: `apps.ai_classroom.models.EnrichedNoteBlock`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `enriched_note` | FK → EnrichedNote | Parent enriched note |
| `block_index` | PositiveInteger | Order in sequence |
| `block_type` | Char(32) | One of: `overview`, `key_concept`, `explanation`, `example`, `gap_fill` |
| `title` | Char(255) | Concise heading (optional) |
| `content` | Text | Generated prose (1-3 sentences) |
| `generation_method` | Char(20) | Enum: `llm`, `rule_based`, `user_edited`, `transcribed` |
| `source_chunk_ids` | JSON[UUID] | NoteChunk IDs used to produce this block |
| `created_at` | DateTime | Creation timestamp |

**Block Types** (from prompt template):
- `overview` - High-level summary
- `key_concept` - Important concept explanation
- `explanation` - Detailed explanation
- `example` - Concrete example
- `gap_fill` - Content filling a detected gap

---

## 3. CitationBlock (Citations & Verification)

**Model**: `apps.ai_classroom.models.CitationBlock`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `enriched_note_block` | OneToOne → EnrichedNoteBlock | Associated block |
| `source_refs` | JSON[Object] | Array of source references |
| `verification_status` | Char(24) | Enum: `supported`, `partially_supported`, `unsupported`, `not_verified` |
| `verification_score` | Float (nullable) | Lexical support score (0.0-1.0) |
| `verifier_version` | Char(64) | Verifier version string (e.g., "sim-v1") |
| `created_at` | DateTime | Creation timestamp |

### Source Reference Structure (`source_refs` array elements)

```json
{
  "source_type": "note" | "reference",
  "chunk_id": "uuid",
  "document_id": "uuid",
  "page_number": integer,
  "revision_id": "uuid" | null,
  "retrieval_score": float | null,
  "content": "string"
}
```

### Verification Status Definitions

- `supported` - Lexical overlap ≥ 0.60 (VERIFIER_SUPPORTED_THRESHOLD)
- `partially_supported` - Lexical overlap ≥ 0.30 (VERIFIER_PARTIAL_THRESHOLD) but < 0.60
- `unsupported` - Lexical overlap < 0.30
- `not_verified` - No source refs provided

### Verification Algorithm

`EvidenceVerifier._lexical_support(block_content, cited_chunk_contents)`:
1. Tokenize both texts (lowercase, alnum only, min length 3)
2. Compute overlap = |block_tokens ∩ chunk_tokens| / |block_tokens|
3. Take maximum overlap across all cited chunks
4. Classify by thresholds

---

## 4. Tags (Document Tags)

**Models**: `Tag`, `DocumentTag`, `TagChangeLog`

### Tag (Stable Academic Concept)
- `subject` → Subject (required anchor)
- `stable_key` - Slugified identifier (immutable identity)
- `display_name` - Human-readable name (can change)
- `parent` → Tag (optional hierarchy)

### DocumentTag (Document-Tag Link)
- `document` → Document
- `tag` → Tag
- `generation_job` → Job (provenance)

### Extraction Method (TaggingService)
- Rule-based: frequent significant tokens from document chunks (min 5 chars, not in stopwords)
- Top 5 tokens by frequency → find-or-create Tag by (subject, stable_key)
- Link to document via DocumentTag

---

## 5. Questions (Generated MCQs)

**Model**: `apps.questions.models.Question`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `document` | FK → Document | Source document |
| `source_chunk_id` | UUID | Chunk used for generation |
| `source_revision_id` | UUID | Revision of source chunk |
| `prompt` | Text | Question stem |
| `options` | JSON[String] | Answer choices (≥2) |
| `answer_index` | Integer | Correct option index |
| `difficulty` | Char(16) | `easy` / `medium` / `hard` |
| `generation_model` | Char(128) | LLM model used |
| `prompt_version` | Char(64) | e.g., "question_generation:v1" |
| `question_key` | Char(32) | MD5(chunk_id:prompt) for idempotency |
| `content_hash` | Char(64) | SHA256 of prompt+options for deduplication |
| `created_at` | DateTime | Creation timestamp |

### QuestionTagLink
Links questions to Tags for topic-based retrieval.

---

## 6. Retrieval Metadata

The pipeline records these metadata points during retrieval:

| Stage | Metadata |
|-------|----------|
| **Retrieve** | `user_chunks` (note chunks from user document), `reference_chunks` (from reference books), `evidence_payload` (both sets with chunk_id + content) |
| **Draft/Gap/Fill** | `llm_provider`, `llm_model`, `prompt_name`, `prompt_version`, `input_tokens`, `output_tokens`, `latency_ms` |
| **Citation Stitch** | Resolves `source_chunk_ids` → full chunk metadata (including page_number, revision_id) |
| **Verification** | `verification_status`, `verification_score`, `verifier_version` per block |

---

## 7. Provider/Model Metadata Persistence

Persisted on `EnrichedNote`:
- `provider` - Actual LLM provider used (e.g., "ollama")
- `model` - Actual model used (e.g., "qwen2.5:7b")
- `prompt_version` - All prompt versions used in this run

---

## 8. Output from `format_output_node`

The final state returned by the enrichment graph:

```python
{
    "all_blocks": [...],              # All draft + fill blocks (pre-stitching)
    "stitched_blocks": [...],         # Blocks with refs resolved + verification
    "draft_result": {...},            # Raw draft LLM output
    "gaps_result": {"gaps": [...]},   # Gap detection output
    "fill_result": {"blocks": [...]}, # Gap fill output
    "llm_provider": "ollama",         # Actual provider
    "llm_model": "qwen2.5:7b",        # Actual model
}
```

Each `stitched_block`:
```python
{
    "index": 0,
    "block_type": "overview",
    "title": "Dijkstra's Algorithm",
    "content": "Dijkstra's algorithm computes shortest paths...",
    "generation_method": "llm",
    "source_chunk_ids": ["uuid1", "uuid2"],
    "refs": [
        {
            "source_type": "note",
            "chunk_id": "uuid1",
            "document_id": "uuid-doc",
            "page_number": 1,
            "revision_id": "uuid-rev",
            "retrieval_score": None,
            "content": "Original chunk text..."
        }
    ],
    "status": "supported",
    "score": 0.75
}
```

---

## 9. Key Invariants

1. **One active EnrichedNote per document** (enforced by unique constraint on document+content_hash where superseded=False)
2. **Every EnrichedNoteBlock has exactly one CitationBlock** (OneToOne)
3. **source_chunk_ids on block must match chunk_ids in citation.source_refs**
4. **Blocks are ordered by block_index**
5. **Verification status is independent of generation_method** - a rule-based block can be unsupported, an LLM block can be supported
6. **Tags are stable by (subject, stable_key)** - renames don't create new tags
7. **Questions are idempotent by (source_revision_id, content_hash, question_key)**

---

## 10. Settings Affecting Output

| Setting | Default | Effect |
|---------|---------|--------|
| `VERIFIER_SUPPORTED_THRESHOLD` | 0.60 | Minimum lexical overlap for "supported" |
| `VERIFIER_PARTIAL_THRESHOLD` | 0.30 | Minimum for "partially_supported" |
| `VERIFIER_VERSION` | "sim-v1" | Version string on CitationBlock |
| `ENRICHMENT_MODEL` | "mock-gpt" | Default model name (overridden by provider) |
| `LLM_PROVIDER_CHAIN` | "mock,mock" | Provider chain (e.g., "ollama" for real) |
| `LLM_DISABLE_FALLBACK` | "0" | If "1", prevents mock fallback in real runs |
| `EMBEDDING_PROVIDER` | "sentence_transformers" | Embedding model for retrieval |
| `EMBEDDING_DIMENSIONS` | 384 | Vector dimension |