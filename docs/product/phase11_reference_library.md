# Phase 11 — Reference Library & Grounded Knowledge

## Status: COMPLETE

**Branch:** `feature/phase-11-reference-library` (branched from `fix/phase-10d-chat-multi-turn-context`)

---

## 1. Overview & Architectural Vision

Prior to Phase 11, StudyAI relied on notes and pre-trained LLM memory for enrichment and chat responses. When a student asked conceptual questions without personal notes or when note enrichment needed deep reference backing, the LLM answered from ungrounded parametric knowledge.

Phase 11 introduces a first-class **Reference Library** allowing students and educators to ingest real textbooks, reference PDFs, and lecture materials into a single, shared pgvector dense & lexical hybrid retrieval pipeline.

### Core Architecture

```
                  Reference Library UI
                           │
             (Upload PDF: Textbook / Notes)
                           ▼
                  POST /api/v1/references/
                           │
             ReferenceDocument (Status: PENDING)
                           │
                Celery Asynchronous Task
           (ingest_reference_document_task)
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
   pypdf Extraction                 qwen3.5:4b Vision
 (Native text / pages)           (Image / Scanned Fallback)
          │                                 │
          └────────────────┬────────────────┘
                           ▼
                 Deterministic Chunking
             (~200 words, 35-word overlap,
             boundaries, content_hash)
                           │
                           ▼
              Qwen/Qwen3-Embedding-0.6B
              (1024-dim dense vectors)
                           │
                           ▼
              PostgreSQL + pgvector
        ReferenceDocument (Status: READY)
          & ReferenceChunk (1024-dim)
                           │
                           ▼
          Shared Reference Retrieval Service
            retrieve_reference_context()
        (Hybrid Dense Cosine + Keyword RRF)
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      Note Enrichment               Ask StudyAI
   (enrichment_nodes.py)        (langgraph_nodes.py)
             │                           │
             └─────────────┬─────────────┘
                           ▼
                      qwen3.5:4b
              (Strict Source Grounding)
```

---

## 2. Canonical Stack Enforcement

- **LLM:** `qwen3.5:4b` (via local Ollama at `http://host.docker.internal:11434`, zero external API dependencies)
- **Embedding:** `Qwen/Qwen3-Embedding-0.6B` (1024-dimensional dense vectors, normalized L2, cosine distance via `vector_cosine_ops` in pgvector)
- **Object Storage:** MinIO / S3-compatible local bucket storage (`studyai`)
- **Background Tasks:** Celery + Redis broker
- **Database:** PostgreSQL 16 + pgvector extension
- **No external fallback / MiniLM:** `all-MiniLM-L6-v2` is strictly superseded by `Qwen/Qwen3-Embedding-0.6B` across all reference retrieval.

---

## 3. Reference Data Models & Schema

Implemented in [`backend/apps/references/models.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/references/models.py):

### `ReferenceDocument`

Represents an ingested reference work (textbook, syllabus, lecture notes):
- `id`: UUID primary key
- `title`: Document title (defaults to sanitised filename stem)
- `source_type`: `TEXTBOOK`, `REFERENCE_PDF`, or `LECTURE_MATERIAL`
- `file_path`: Storage key in object storage (MinIO)
- `subject`: Foreign key to `Subject` (optional subject scoping)
- `profile`: Foreign key to `Profile` (optional private profile scoping; `NULL` indicates global library document)
- `status`: `PENDING` → `PROCESSING` → `READY` (or `FAILED`)
- `page_count`: Integer total pages extracted
- `chunk_count`: Integer total chunks indexed
- `error_message`: Failure diagnostic if status is `FAILED`
- `metadata`: JSON field preserving filename, file size, SHA256, extraction stats
- `created_at`, `updated_at`: Timestamps

### `ReferenceChunk`

Represents a single retrieval chunk with complete provenance:
- `id`: UUID primary key
- `reference_document`: Foreign key (CASCADE delete)
- `chunk_index`: 0-indexed sequential chunk counter
- `text`: Chunk content text
- `embedding`: `AdaptiveVectorField(dimensions=1024)` indexed with HNSW cosine distance
- `page_number`: 1-indexed source PDF page number
- `chapter`: Extracted or detected chapter title
- `section`: Extracted section heading
- `content_hash`: SHA-256 hash for deduplication
- `metadata`: JSON field for supplementary markers

---

## 4. Extraction & Deterministic Chunking

### PDF Extraction Pipeline (`backend/apps/references/extraction.py`)
1. **Direct Digital Extraction:** Uses `pypdf.PdfReader` to extract native page text and detect layout.
2. **Vision OCR Fallback:** Pages with fewer than 30 characters of extracted text (e.g. scanned pages, diagrams, handwritten slides) automatically invoke `qwen3.5:4b` vision OCR.
3. Preserves exact 1-indexed page provenance for every page extracted.

### Textbook Chunking Engine (`backend/apps/references/chunking.py`)
- Target size: ~200 words per retrieval chunk.
- Overlap: 35 words between consecutive chunks to maintain semantic continuity across boundaries.
- Boundary Respect: Automatically detects Chapter (`Chapter \d+:? [^\n]+`) and Section (`\d+\.\d+ [^\n]+`) headers. When a header is encountered, the previous chunk is immediately flushed to prevent mixing disparate chapters/topics.
- SHA-256 `content_hash` generated for each chunk.

---

## 5. Ingestion Workflow & Async Tasks

Implemented in [`backend/apps/references/ingestion.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/references/ingestion.py) & [`backend/apps/references/tasks.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/references/tasks.py):

1. **HTTP Upload:** Client uploads PDF via `POST /api/v1/references/`. File is streamed into MinIO (`references/<uuid>/<filename>`). A `ReferenceDocument` record is created in `PENDING` state. HTTP response returns `201 Created` immediately.
2. **Celery Task Dispatch:** Celery worker consumes `ingest_reference_document_task(reference_id)`.
3. **Status Transition:** Document transitions to `PROCESSING`.
4. **Extraction & Chunking:** Extracts text from MinIO file, partitions into chunks with provenance.
5. **Batch Embedding:** Uses canonical `Qwen/Qwen3-Embedding-0.6B` provider in batches of 32 to generate 1024-dimensional vectors.
6. **Atomic Persistence:** Chunks are bulk-inserted with pgvector embeddings, and document transitions to `READY` with `page_count` and `chunk_count`.
7. **Failure Handling:** Any unrecoverable exception transitions document to `FAILED` and records `error_message`.

---

## 6. Shared Reference Retrieval Service

Implemented in [`backend/apps/references/services.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/references/services.py):

```python
def retrieve_reference_context(
    query: str,
    *,
    profile=None,
    subject=None,
    top_k: int = 5,
    min_similarity: float = 0.35,
) -> list[dict]:
```

### Hybrid Retrieval & Reciprocal Rank Fusion (RRF)
1. **Dense Vector Search:** Embeds query using `Qwen/Qwen3-Embedding-0.6B` (1024-dim), queries pgvector using `CosineDistance('embedding', query_vector)` with index acceleration.
2. **Keyword Full-Text Search:** Runs PostgreSQL `to_tsquery('english', query)` against chunk text with `SearchRank`.
3. **RRF Merge:** Combines rankings using $RRF\_Score = \sum \frac{1}{60 + rank}$ to provide robust recall for exact keywords, code tokens, and semantic matches alike.
4. **Scoping & Authorization:**
   - Always filters to documents where `status == READY`.
   - Respects profile isolation: chunks from private references are only visible if `profile == requested_profile`. Global references (`profile IS NULL`) are accessible to all authorized profiles.
   - Respects subject filtering: when `subject` is provided, filters to documents mapped to that subject or global references.
5. **Standardized Evidence Format:**
   Returns structured evidence dictionaries with `text`, `source_id`, `source_type="reference"`, `document_title`, `page_number`, `chapter`, `section`, and `similarity`.

---

## 7. Integration with Features

### 1. Note Enrichment (`backend/apps/ai_classroom/enrichment_nodes.py`)
- Updated `retrieve_chunks_node`: Queries both student note chunks and shared reference library chunks via `retrieve_reference_context`.
- Updated `draft_node`: Grounding prompt strictly mandates:
  - If reference evidence is present: incorporate authoritative definitions and cite textbook name, chapter, and page.
  - If no reference evidence is present: answer strictly from student notes without inventing textbook citations.

### 2. Ask StudyAI Chatbot (`backend/apps/chat/langgraph_nodes.py`)
- Integrated into `retrieval_node`: Retrieves authoritative reference context alongside student notes.
- Updated `answer_generation_node`: Formats reference evidence into the LLM system prompt with textbook title, chapter, section, and page number.
- Verified evidence graph routing (`chat_graph.py`): When no evidence chunks exist, bypasses redundant evidence verification retries to avoid wasting compute.
- Multi-turn context: Preserves conversation history across turns as verified in Phase 10D.

---

## 8. Frontend Reference Library UI

Implemented in [`frontend/src/components/references/ReferenceLibraryPage.tsx`](file:///Users/yash/CV_Project/StudyAI/frontend/src/components/references/ReferenceLibraryPage.tsx):

- **Routing:** Available at `/references`, `/subjects/:subjectId/references`, and `/ai-classroom/references`.
- **Subject Workspace Integration:** Added Reference Library quick-access card and workspace action button in `SubjectWorkspace.tsx`.
- **Document Management:**
  - Responsive card grid displaying document title, source type badge (`Textbook`, `Reference PDF`, `Lecture Material`), scope badge (`Global`, `Private`), and subject tag.
  - Live status badges: `✓ Ready` (green), `⏳ Processing...` (amber with pulse), `Queued` (blue), and `Failed` (red with error message).
  - Provenance footer displaying `X pages · Y chunks indexed` and creation date.
- **Upload Modal:** Dialog with file picker (`.pdf`), title auto-fill, source type selector, subject dropdown, and global/private scope selector.
- **Live Status Polling:** Auto-polls every 3 seconds while any document is in `PENDING` or `PROCESSING` state, stopping once all documents settle.
- **Cascade Deletion:** Confirm dialog with atomic removal of document, MinIO storage object, chunks, and pgvector embeddings.

---

## 9. Verification & Test Results

### 1. Backend Unit & Integration Tests (15 / 15 Passed)
`pytest tests/unit/test_reference_library.py -v`

| Test Case | Description | Result |
|-----------|-------------|--------|
| `test_create_reference_document` | Verifies document creation with defaults and metadata | ✅ PASS |
| `test_global_scope_document` | Verifies platform-wide reference with `profile=None` | ✅ PASS |
| `test_reference_chunk_provenance` | Verifies chunk provenance fields (page, chapter, section) | ✅ PASS |
| `test_deterministic_textbook_chunking` | Verifies ~200 word target, 35 word overlap, and boundary splits | ✅ PASS |
| `test_direct_pdf_extraction` | Verifies native PDF text extraction with page numbers | ✅ PASS |
| `test_ocr_fallback_for_scanned_low_text_page` | Verifies vision OCR invocation on scanned/low-text pages | ✅ PASS |
| `test_ingestion_success` | Verifies full async task workflow from PENDING to READY | ✅ PASS |
| `test_ingestion_failure_records_error` | Verifies status FAILED and error recording on bad file | ✅ PASS |
| `test_cascade_deletion` | Verifies deleting document cascades to chunks and embeddings | ✅ PASS |
| `test_profile_isolation` | Verifies Profile A cannot retrieve Profile B's private references | ✅ PASS |
| `test_global_scope_accessible_to_all_profiles` | Verifies global reference is retrieved by all profiles | ✅ PASS |
| `test_ranking_and_query_similarity` | Verifies dense similarity ranking of relevant chunks | ✅ PASS |
| `test_enrichment_incorporates_reference_chunks` | Verifies enrichment node integrates reference material | ✅ PASS |
| `test_enrichment_no_reference_fallback` | Verifies fallback instructions when no reference exists | ✅ PASS |
| `test_chat_retrieves_reference_material_and_preserves_multi_turn` | Verifies chatbot receives reference context and preserves history | ✅ PASS |

### 2. Multi-Turn Regression Suite (7 / 7 Passed)
`pytest tests/unit/test_chat_multi_turn.py -v`
All 7 multi-turn regression tests from Phase 10D pass with zero regressions.

### 3. Frontend Unit Tests (73 / 73 Passed)
`npm test` in `frontend/`
All 11 test suites and 73 unit tests pass.

### 4. Browser E2E Acceptance Test (10 / 10 Verified)
`node frontend/tests/e2e/phase11_acceptance.mjs`

| Checkpoint | Action / Criterion | Result |
|------------|-------------------|--------|
| `authenticated` | Log in as `admin@studyai.dev` & activate `YashAI` | ✅ PASS |
| `subjectWorkspaceLoaded` | Load subject workspace & verify Reference Library link | ✅ PASS |
| `referenceLibraryNavigated` | Navigate to `/subjects/:id/references` | ✅ PASS |
| `uploadDialogOpen` | Open Upload Reference Dialog modal | ✅ PASS |
| `documentUploaded` | Submit PDF upload and see card appear in list | ✅ PASS |
| `ingestionCompletedReady` | Ingestion task finishes; card transitions to `✓ Ready` | ✅ PASS |
| `provenanceMetadataDisplayed` | Card displays `2 pages · 2 chunks indexed` and badges | ✅ PASS |
| `askStudyAIGroundedAnswer` | Turn 1: Ask grounded question; receives BFS/FIFO answer | ✅ PASS |
| `multiTurnContextPreserved` | Turn 2: Ask follow-up "What is its running time?"; receives $O(V+E)$ | ✅ PASS |
| `documentDeletedSuccessfully` | Delete reference; confirm dialog cleans up document & chunks | ✅ PASS |

**Recorded Artifacts:**
- Result JSON: [`frontend/tests/e2e/phase11_results.json`](file:///Users/yash/CV_Project/StudyAI/frontend/tests/e2e/phase11_results.json)
- Screenshots:
  - `01_authenticated.png`
  - `02_subject_workspace.png`
  - `03_reference_library_empty.png`
  - `04_upload_dialog_open.png`
  - `05_document_uploaded_pending.png`
  - `06_document_ready.png`
  - `07_grounded_answer_turn1.png`
  - `08_grounded_answer_turn2.png`
  - `09_delete_confirm_dialog.png`
  - `10_deletion_verified.png`

---

PHASE 11 COMPLETE
