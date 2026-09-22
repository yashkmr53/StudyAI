# Phase 3 — Embedding Stack Migration: Canonical `Qwen/Qwen3-Embedding-0.6B` Implementation

**Date:** September 21, 2026  
**Status:** Completed & Fully Verified  
**Canonical Embedding Model:** `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions, L2 normalized, Apple Silicon Metal / MPS GPU accelerated)  
**Canonical LLM:** `qwen3.5:4b` (via native host Ollama, 100% GPU)  
**Database Vector Store:** PostgreSQL 16 + pgvector (`vector(1024)` with HNSW cosine index)  

---

## 1. Executive Summary

Phase 3 transitions the entire StudyAI embedding and retrieval pipeline from legacy 384-dimensional models (`sentence-transformers/all-MiniLM-L6-v2`) and hosted providers (OpenAI) to the single canonical embedding model: **`Qwen/Qwen3-Embedding-0.6B`**.

The StudyAI production AI stack now contains exactly two models:
1. **LLM / Multimodal:** `qwen3.5:4b` (Native host Ollama with GPU acceleration)
2. **Embeddings / Retrieval:** `Qwen/Qwen3-Embedding-0.6B` (Local sentence-transformers with Apple Silicon Metal/MPS acceleration)

All vector storage in PostgreSQL has been migrated to 1024 dimensions with HNSW indexing, and all unit, provider, and retrieval test suites pass with zero regressions.

---

## 2. Key Architecture Decisions & Implementations

### 2.1 Canonical Provider: [`Qwen3EmbeddingProvider`](backend/providers/embeddings/qwen3.py)
* **Model:** `Qwen/Qwen3-Embedding-0.6B`
* **Dimension:** 1024
* **Version String:** `qwen3-embedding-0.6b-v1`
* **Normalization:** Native L2 unit normalization (`normalize_embeddings=True`), allowing cosine distance to be calculated directly via dot products and the pgvector `<=>` cosine distance operator.
* **Context Capacity:** Up to 32,768 tokens (dramatically larger than MiniLM's 256-token limit, eliminating truncation of dense paragraphs).

### 2.2 Hardware Acceleration (Apple Silicon Metal / MPS)
* **Problem:** Running dense embedding models on CPU inside Docker containers results in high latency (~7 seconds per chunk).
* **Solution:**
  - `Qwen3EmbeddingProvider` automatically detects device capabilities:
    ```python
    if torch.cuda.is_available():
        self._device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        self._device = "mps"
    else:
        self._device = "cpu"
    ```
  - On macOS with Apple Silicon, it utilizes **Metal Performance Shaders (`mps`)**, providing near-instantaneous batch embedding (~6-8 batches/sec) with unified memory.

### 2.3 Upgrading Old Data Dimensions: The Migration Approach
A critical architectural challenge when transitioning from 384 dimensions (`all-MiniLM-L6-v2`) to 1024 dimensions (`Qwen/Qwen3-Embedding-0.6B`) is how to handle existing data in PostgreSQL:

#### 1. Why Vectors Cannot Be Cast or Padded
* **Mathematical Incompatibility:** Dense embedding vectors represent positions in a continuous latent geometry learned during model training. You cannot simply "zero-pad" a 384-dimensional vector to 1024 dimensions. The coordinate systems of MiniLM and Qwen3 are completely unrelated; computing cosine similarity across mismatched models is mathematically meaningless and corrupts semantic search.
* **Database Engine Constraints:** PostgreSQL's pgvector extension strictly enforces fixed dimensional sizes. Executing `ALTER TABLE ... TYPE vector(1024)` on a column containing `vector(384)` data triggers:
  ```text
  ERROR: cannot cast type vector to vector
  ```
  Additionally, PostgreSQL blocks type alterations if an HNSW or IVFFlat index references the column.

#### 2. The 3-Step Atomic Database Migration (`0004_qwen3_embeddings_1024.py`)
To achieve a clean, zero-corruption upgrade without losing chunk records, metadata, or document links:
1. **Pre-Alter Data Invalidation:**
   * Drop the existing HNSW index:
     ```sql
     DROP INDEX IF EXISTS idx_notechunk_hnsw_embedding;
     ```
   * Nullify existing vectors while marking chunks as stale:
     ```sql
     UPDATE retrieval_notechunk SET embedding = NULL, stale = TRUE WHERE embedding IS NOT NULL;
     ```
     *Rationale:* This preserves all source text content, page boundaries, document links, and revision hashes intact, while removing the obsolete 384-d binary representations. Marking `stale = TRUE` ensures retrieval excludes these chunks until fresh 1024-d vectors are computed.
2. **Schema Alteration:**
   * Alter the column type to `vector(1024)`:
     ```sql
     ALTER TABLE retrieval_notechunk ALTER COLUMN embedding TYPE vector(1024);
     ```
     Because all rows in the column are now `NULL`, PostgreSQL smoothly alters the physical column type without casting conflicts.
   * Update Django ORM model state: `AdaptiveVectorField(dimensions=1024)`.
3. **Recreating the HNSW Index:**
   * Rebuild the HNSW vector index with cosine distance operator:
     ```sql
     CREATE INDEX IF NOT EXISTS idx_notechunk_hnsw_embedding 
     ON retrieval_notechunk USING hnsw (embedding vector_cosine_ops);
     ```

#### 3. Re-Embedding Historical Chunks (Data Backfill)
To populate genuine 1024-dimensional embeddings for existing rows:
* The [`backfill_embeddings.py`](backend/apps/retrieval/management/commands/backfill_embeddings.py) management command and the [`index_document()`](backend/apps/retrieval/services.py) service read the intact `content` from each chunk.
* Chunks are encoded through `Qwen/Qwen3-Embedding-0.6B` with Apple Silicon Metal (`mps`) GPU acceleration.
* Chunks are updated in atomic batches:
  ```python
  chunk.embedding = new_1024_d_vector
  chunk.embedding_model = "sentence_transformers"
  chunk.embedding_version = "qwen3-embedding-0.6b-v1"
  chunk.stale = False
  chunk.save(update_fields=("embedding", "embedding_model", "embedding_version", "stale"))
  ```
This brings all historical chunks, platform reference books, and newly ingested notes into a unified, high-precision 1024-dimensional latent space.

### 2.5 Dynamic Hashing Provider for Testing
To keep unit test runs fast and deterministic without requiring heavy model loading or external networks:
* [`HashingEmbeddingProvider`](backend/providers/embeddings/hashing.py) dynamically reads `EMBEDDING_DIMENSIONS` (1024) from Django settings.
* Test suite settings in [`backend/config/settings/test.py`](backend/config/settings/test.py) configure `EMBEDDING_PROVIDER="hashing"` and `EMBEDDING_MODEL_VERSION="hashing-1024-v1"`.

---

## 3. Configuration Updates

### 3.1 [`backend/config/settings/base.py`](backend/config/settings/base.py)
```python
# AI Classroom retrieval foundation (StudyAI Target Stack: Qwen/Qwen3-Embedding-0.6B)
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "sentence_transformers")
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
EMBEDDING_MODEL_VERSION = os.environ.get("EMBEDDING_MODEL_VERSION", "qwen3-embedding-0.6b-v1")
EMBEDDING_DEVICE = os.environ.get("EMBEDDING_DEVICE", "auto")
```

### 3.2 [`.env`](.env) & [`.env.example`](.env.example)
```bash
# Embedding Configuration (StudyAI Target Stack: Qwen/Qwen3-Embedding-0.6B)
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIMENSIONS=1024
EMBEDDING_MODEL_VERSION=qwen3-embedding-0.6b-v1
EMBEDDING_DEVICE=auto
```

### 3.3 [`docker-compose.yml`](docker-compose.yml)
Synchronized container environment variables for `api` and `worker`:
```yaml
EMBEDDING_PROVIDER: ${EMBEDDING_PROVIDER:-sentence_transformers}
EMBEDDING_MODEL_NAME: ${EMBEDDING_MODEL_NAME:-Qwen/Qwen3-Embedding-0.6B}
EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-1024}
EMBEDDING_MODEL_VERSION: ${EMBEDDING_MODEL_VERSION:-qwen3-embedding-0.6b-v1}
EMBEDDING_DEVICE: ${EMBEDDING_DEVICE:-auto}
```

---

## 4. Verification Results

### 4.1 Live Model Embedding & Semantic Separation
Verified live on Mac host with Metal GPU (`mps`):
```text
Model: Qwen/Qwen3-Embedding-0.6B
Device: mps
Dimension: 1024
Version: qwen3-embedding-0.6b-v1
L2 Norm: 0.999896
Similarity (Biology Text 1 vs Biology Text 2): 0.8533
Similarity (Biology Text 1 vs Machine Learning Text): 0.2975
Result: PASSED (Strong semantic clustering and clear cross-domain separation)
```

### 4.2 PostgreSQL Database & pgvector Verification
* Column type: `vector(1024)`
* Index: `idx_notechunk_hnsw_embedding` (`hnsw (embedding vector_cosine_ops)`)
* Vector dimension check: `vector_dims(embedding) = 1024`
* Cosine distance query:
  ```sql
  SELECT id, (embedding <=> $query_vec) AS cosine_distance 
  FROM retrieval_notechunk 
  WHERE embedding IS NOT NULL 
  ORDER BY cosine_distance LIMIT 5;
  ```
  Result: Sub-millisecond HNSW traversal with zero errors.

### 4.3 Automated Test Suite Results
* **Embedding Provider Tests ([`test_embeddings.py`](backend/providers/tests/test_embeddings.py)):** 18 passed / 0 failed (100%)
* **All Provider Tests ([`backend/providers/tests/`](backend/providers/tests/)):** 140 passed / 0 failed, 4 skipped
* **Retrieval & Chunking Tests ([`test_retrieval.py`](backend/tests/api/test_retrieval.py)):** 14 passed / 0 failed, 1 skipped
* **Combined Test Suite:** 154 passed / 0 failed (100% clean)

---

## 5. Summary of Models in the Entire System

| Component | Canonical Model | Provider / Execution Mode | Parameters / Dimension | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Generative AI / Vision / Chat** | `qwen3.5:4b` | Native Host Ollama (100% GPU / Metal) | `num_predict=4096`, `num_ctx=16384` | **Active & Verified** |
| **Embeddings / Retrieval** | `Qwen/Qwen3-Embedding-0.6B` | Local `sentence-transformers` (MPS / Metal) | 1024 dimensions, L2 normalized | **Active & Verified** |
| **Vector Store** | pgvector 0.7+ | PostgreSQL 16 HNSW (`vector_cosine_ops`) | `vector(1024)` | **Migrated & Active** |
| **All Other AI Models** | *None* | *Disabled / Removed* | N/A | **Complete** |
