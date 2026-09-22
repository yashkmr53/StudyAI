# Phase 1 — Current AI Architecture Audit

**Date:** September 21, 2026  
**Status:** Audit Only (No production modifications)  
**Target Production Architecture:**
* **LLM / Multimodal:** `qwen3.5:4b` (OCR, chat, gap detection, enrichment, questions, tags, explanations)
* **Embeddings:** `Qwen/Qwen3-Embedding-0.6B` (note & reference embeddings, pgvector retrieval)
* **Production Fallbacks:** None (isolated mocks only in unit tests)

---

## 1. Executive Summary & Scorecard

| Capability | Current Implementation | Status | Action Required for Target Stack |
| :--- | :--- | :--- | :--- |
| **LLM** | `OllamaLLMProvider` + `LLMChainProvider` pointing to `qwen2.5:7b` (with fallback to mock in default config). Only implements `generate_structured(...)`; lacks unstructured text generation and multimodal vision inputs. | `PARTIAL` | **Replace:** Build canonical `Qwen35Provider` supporting `generate`, `generate_structured`, `generate_with_image`, and `generate_structured_with_image` targeting `qwen3.5:4b`. Remove multi-provider fallback in production. |
| **OCR** | `TesseractOCRProvider` (via `tesserocr` C bindings; crashes on startup via `get_tesseract_version()`, silently falling back to `MockOCRProvider` generating synthetic hashes). `PaddleOCRProvider` present but uninstalled. | `BROKEN` | **Replace:** Deprecate legacy Tesseract and PaddleOCR engines. Route image OCR directly through `qwen3.5:4b` vision capabilities for faithful line-by-line transcription. |
| **Embeddings** | `SentenceTransformerEmbeddingProvider` using `sentence-transformers/all-MiniLM-L6-v2` producing 384-dimensional dense vectors stored in pgvector `vector(384)`. | `PARTIAL` | **Replace:** Build `Qwen3EmbeddingProvider` wrapping `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions). Update database column from `vector(384)` to `vector(1024)` via Django migration and re-index. |
| **Retrieval** | `RetrievalService.search` hybrid dense pgvector cosine + keyword tsvector RRF fusion ($k=60$). Correctly scopes queries with `profile_id=None` when `reference_only=True`. | `COMPLETE` | **Reuse:** Keep hybrid retrieval and RRF fusion architecture. Update query vector generator to use 1024-d embeddings from `Qwen/Qwen3-Embedding-0.6B`. |
| **Chatbot** | `ChatService` and LangGraph `chat_graph` running RAG retrieval and structured response generation. | `COMPLETE` | **Reuse:** Keep agent and chat graph infrastructure. Direct LLM calls through the canonical `qwen3.5:4b` provider. |
| **Gap Detection** | 3-node LangGraph candidate pipeline (`candidate_generation` using sliding n-grams in `gap_candidates.py` -> `coverage_comparison` -> `candidate_validation` using Qwen 4-way classification). | `PARTIAL` | **Replace:** Eliminate complex candidate generator heuristics and K-subset gates. Implement direct `qwen3.5:4b` gap detection prompt taking user note + retrieved reference chunks and returning structured gaps (`MISSING`, `PARTIALLY_COVERED`). |
| **Enrichment** | `gap_fill_node` prompts LLM with schema validation for explanation blocks, key concepts, and examples. | `COMPLETE` | **Reuse / Adapt:** Maintain structured schema enforcement. Route generation through `qwen3.5:4b`, focusing on concise explanations for detected gaps while preserving user note text. |
| **Citation Validation** | `EvidenceVerifier` computes token lexical overlap (`supported`, `partially_supported`, `unsupported`) between block content and chunk text. | `PARTIAL` | **Adapt:** Update to deterministically verify the exact `reference_quote` extracted by `qwen3.5:4b` against the backing `NoteChunk.content`. Reject unsupported citations. |
| **Persistence** | Atomic PostgreSQL transaction in `run_enrichment_job` persisting `EnrichedNote`, `EnrichedNoteBlock`, `CitationBlock`, `DocumentTag`, and `PracticeQuestion`. Auto-marks stale on re-index. | `COMPLETE` | **Reuse:** Keep multi-table atomic transactional persistence boundary and version tracking. |
| **Profile API** | REST endpoints `GET /api/v1/documents/{id}/enrichment` and `POST /api/v1/documents/{id}/enrichment` returning serialized enriched notes and triggering jobs. | `COMPLETE` | **Reuse:** Keep REST APIs. Expose reference quotes and book citations cleanly in the serialized response. |
| **Profile UI** | React component `EnrichedView.tsx` renders blocks, loading states, stale alerts, and retry actions. Citations currently navigate to student note pages rather than showing textbook sources. | `PARTIAL` | **Adapt:** Update citation UI component to display reference book titles and quote evidence tooltips alongside student note page anchors. |

---

## 2. In-Depth Subsystem Audit

### 2.1 LLM Providers & Configuration
* **Active Code:** [`backend/providers/llm/local.py`](backend/providers/llm/local.py), [`backend/providers/llm/chain.py`](backend/providers/llm/chain.py), [`backend/providers/registry.py`](backend/providers/registry.py).
* **Current Model Configuration:**
  - `LLM_MODEL`: defaults to `qwen2.5:7b` in `.env`, but hardcoded fallback to `llama3.1:8b` exists in `local.py:47`.
  - `LLM_PROVIDER_CHAIN`: supports comma-separated fallback (e.g. `ollama,mock`).
  - `LLM_DISABLE_FALLBACK`: added to prevent silent fallback to mock.
* **Limitations Identified:**
  - `OllamaLLMProvider` only implements `generate_structured(self, *, prompt, schema, request_id)`.
  - There is no plain text `generate(self, ...)` method.
  - There is no multimodal image method (`generate_with_image`, `generate_structured_with_image`).
  - `LLMProvider` protocol in [`backend/providers/base.py`](backend/providers/base.py#L46) only declares `generate_structured`.
* **Target Alignment:**
  - `qwen3.5:4b` (backed by the local 4.4B multimodal model with vision, completion, tools, and thinking capabilities) is already pulled and verified in the local Ollama daemon (`http://ollama:11434`).
  - A unified `Qwen35Provider` must be built to handle both text and image/vision prompts with zero fallback to mock in production.

---

### 2.2 OCR Stack
* **Active Code:** [`backend/providers/ocr/local.py`](backend/providers/ocr/local.py), [`backend/apps/documents/services.py:189`](backend/apps/documents/services.py#L189).
* **Current State:**
  - `TesseractOCRProvider` fails on container boot because of `tesserocr.get_tesseract_version()` (`AttributeError`), immediately falling back to `MockOCRProvider`.
  - `MockOCRProvider` produces 3 dummy synthetic lines (`"line_0_..."`).
  - `PaddleOCRProvider` exists in code but dependencies are not installed in the Docker image.
* **Architectural Gap:**
  - Real handwriting OCR has never functioned in production because of this crash and lack of an HTR model.
  - OCR currently runs in a separate Celery task `run_ocr_job` that creates `DocumentLine` records on `DocumentPageRevision`.
* **Target Alignment:**
  - `qwen3.5:4b` has native vision capabilities (`architecture: qwen3vl`).
  - Migrating OCR to `qwen3.5:4b` will eliminate external C-extension dependencies (`tesserocr`, `leptonica`, `tesseract-ocr`, `paddleocr`) and provide superior handwriting recognition.

---

### 2.3 Embeddings & pgvector Schema
* **Active Code:** [`backend/providers/embeddings/local.py`](backend/providers/embeddings/local.py), [`backend/apps/retrieval/models.py`](backend/apps/retrieval/models.py).
* **Current Dimension:** **384** (via `sentence-transformers/all-MiniLM-L6-v2`).
* **Database Field:**
  ```python
  # backend/apps/retrieval/models.py:70
  EMBEDDING_DIMENSIONS = int(getattr(settings, "EMBEDDING_DIMENSIONS", 384))
  embedding = AdaptiveVectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
  ```
* **Target Model Analysis (`Qwen/Qwen3-Embedding-0.6B`):**
  - Inspected HuggingFace Hub configuration (`Qwen/Qwen3-Embedding-0.6B/config.json`).
  - Hidden size / Vector dimension: **1024** (not 384).
  - Framework: Fully compatible with `sentence-transformers >= 3.0` (installed: `sentence-transformers 6.1.0`).
* **Migration Impact:**
  - `EMBEDDING_DIMENSIONS` in `settings/base.py` must change from `384` to `1024`.
  - PostgreSQL table `apps_retrieval_notechunk` has an active column `vector(384)`. A schema migration is required to change it to `vector(1024)`.
  - All existing 768 reference chunks and any user chunks must be wiped and re-indexed with 1024-d vectors.

---

### 2.4 Retrieval Subsystem
* **Active Code:** [`backend/apps/retrieval/retrieval.py`](backend/apps/retrieval/retrieval.py).
* **Architecture:**
  - Hybrid dense cosine search via pgvector + full-text search via PostgreSQL `tsvector_content`.
  - Reciprocal Rank Fusion (RRF) with constant $k=60$.
  - Scoping parameter: `reference_only=True` strictly restricts queries to `profile_id__isnull=True`, preventing data leakage from student notes into reference contexts.
* **Target Alignment:**
  - Retrieval logic is robust, tested, and high-performing. It can be completely reused once vectors are upgraded to 1024 dimensions.

---

### 2.5 Gap Detection & Candidate Pipeline
* **Active Code:** [`backend/apps/ai_classroom/enrichment_nodes.py`](backend/apps/ai_classroom/enrichment_nodes.py), [`backend/apps/ai_classroom/gap_candidates.py`](backend/apps/ai_classroom/gap_candidates.py), [`backend/ai/langgraph/graphs/enrichment_graph.py`](backend/ai/langgraph/graphs/enrichment_graph.py).
* **Current State:**
  - LangGraph graph currently chains:
    `retrieve -> draft -> candidate_generation -> coverage_comparison -> candidate_validation -> gap_fill -> citation_stitch -> evidence_verification -> format_output`
  - `candidate_generation_node`: Runs heuristic sliding n-grams (which was shown to produce 82.9% noise).
  - `coverage_comparison_node`: Classifies candidates into COVERED/MISSING via token checks.
  - `candidate_validation_node`: Batches candidates to Qwen 4-way classifier.
* **Target Alignment:**
  - Per migration instructions, **do not recreate the previous candidate-generation research architecture**.
  - `gap_candidates.py` and multi-step candidate filtering will be decommissioned in Phase 5 in favor of a direct, single-pass gap detection prompt on `qwen3.5:4b` using the note and retrieved reference passages.

---

### 2.6 Chatbot & Agentic Orchestration
* **Active Code:** [`backend/apps/chat/services.py`](backend/apps/chat/services.py), [`backend/ai/langgraph/graphs/chat_graph.py`](backend/ai/langgraph/graphs/chat_graph.py), [`backend/apps/agents/services/agent.py`](backend/apps/agents/services/agent.py).
* **Current State:**
  - Chat routes queries through `chat_graph`, executes RAG search via `RetrievalService`, generates answers with `get_llm_provider()`, and verifies citations.
  - Supports SSE streaming via `_tokenize`.
* **Target Alignment:**
  - Fully compatible with `qwen3.5:4b`. Only needs to consume the canonical `Qwen35Provider`.

---

### 2.7 Question Generation & Taxonomy Tagging
* **Questions:** [`backend/apps/questions/question_generation_nodes.py`](backend/apps/questions/question_generation_nodes.py) generates structured multiple-choice questions from note chunks using `llm.generate_structured(...)`. Works with `qwen3.5:4b`.
* **Tags:** [`backend/apps/ai_classroom/tagging.py`](backend/apps/ai_classroom/tagging.py) currently extracts tags via simple token frequency counting (`_significant_tokens`). It can be upgraded to semantic categorization with `qwen3.5:4b`.

---

### 2.8 Celery Worker & Persistence
* **Active Code:** [`backend/apps/jobs/services.py`](backend/apps/jobs/services.py), [`backend/apps/ai_classroom/services.py`](backend/apps/ai_classroom/services.py).
* **State Machine:**
  - Celery worker processes `Job` rows: `ocr` -> `index` -> `enrich`.
  - Atomic persistence boundary writes `EnrichedNote`, `EnrichedNoteBlock`, `CitationBlock`, `DocumentTag`, and `PracticeQuestion` in a single transaction.
  - Job execution checkpoints allow resuming from last completed LangGraph node.
* **Target Alignment:**
  - Robust infrastructure; completely preserved.

---

### 2.9 Profile API & Frontend UI
* **Active Code:**
  - Backend: `apps/documents/views.py`, `apps/ai_classroom/views.py`, `apps/ai_classroom/views_serializers.py`.
  - Frontend: `frontend/src/features/workspace/SubjectWorkspace.tsx`, `frontend/src/components/notes/EnrichedView.tsx`.
* **Current State:**
  - Note upload and viewing work.
  - Citations display student note page chips (`Page 1`) instead of displaying reference book titles or evidence quote tooltips.
* **Target Alignment:**
  - Update `EnrichedView.tsx` to display reference quote popovers and textbook attribution alongside page chips.

---

## 3. Phase 1 Checkpoint Summary

### 1. What Can Be Reused
* **Core Web & Async Stack:** Django 5, Celery worker + Redis broker, MinIO object storage, PostgreSQL 16 + pgvector.
* **Data Models:** `Profile`, `Subject`, `Document`, `DocumentPage`, `DocumentPageRevision`, `DocumentLine`, `NoteChunk`, `EnrichedNote`, `EnrichedNoteBlock`, `CitationBlock`, `ReferenceBook`.
* **Retrieval Engine:** `RetrievalService.search` hybrid dense pgvector cosine + keyword tsvector RRF fusion and reference scoping logic.
* **Chat & Question Pipelines:** LangGraph `chat_graph` and `question_generation_nodes`.
* **Persistence & Job Infrastructure:** Atomic multi-table commits, checkpoint recovery, and state transitions (`QUEUED` -> `RUNNING` -> `SUCCEEDED`).
* **Frontend Foundations:** Workspace upload workflow, note tabs, and state-driven `EnrichedView.tsx`.

### 2. What Must Be Replaced
* **LLM Layer:** Remove multi-provider routing and fallback to mock; replace with a single, canonical `Qwen35Provider` targeting `qwen3.5:4b` for both structured text and multimodal image calls.
* **OCR Layer:** Completely eliminate `TesseractOCRProvider`, `PaddleOCRProvider`, `MockOCRProvider`, and `tesserocr` C bindings. Replace with `qwen3.5:4b` vision-based transcription.
* **Embedding Layer:** Replace `sentence-transformers/all-MiniLM-L6-v2` with `Qwen/Qwen3-Embedding-0.6B`.
* **Vector Schema:** Migrate `NoteChunk.embedding` column from `vector(384)` to `vector(1024)` in PostgreSQL.
* **Gap Detection Architecture:** Remove the candidate generation research architecture (`gap_candidates.py`, sliding n-grams, 4-way candidate classifier, hard gates) in favor of a direct, single-pass LLM prompt.

### 3. What Is Missing for the Final Product Flow
* **Multimodal OCR Service:** Implementation of vision-to-text prompt on `qwen3.5:4b` to turn uploaded note images into faithful line text.
* **Qwen3 Embedding Provider:** Provider class to generate 1024-d embeddings using `Qwen/Qwen3-Embedding-0.6B`.
* **Re-indexing Command:** Pipeline to clear old 384-d vectors and populate 1024-d vectors for all reference material.
* **Direct Gap Detection Node:** Streamlined LangGraph node that prompts `qwen3.5:4b` with user note + retrieved reference chunks to return structured educational gaps and citations.
* **End-to-End Trigger:** Wiring note indexing completion directly into the enrichment job queue so notes enrich automatically upon upload.
* **Reference Citation UI:** Updating `EnrichedView.tsx` to render textbook titles and quote evidence.
