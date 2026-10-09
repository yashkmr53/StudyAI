# Phase 14: Enrichment Architecture Cleanup Verification Report

## Executive Summary

Phase 14 simplified and cleaned StudyAI’s note-enrichment pipeline into the smallest reliable, evidence-grounded workflow:

$$\text{Note + Retrieved References} \longrightarrow \text{LLM Gap Analysis} \longrightarrow \text{LLM Enrichment} \longrightarrow \text{Citation Validation} \longrightarrow \text{Persistence}$$

### Key Accomplishments
1. **Elimination of Legacy Candidate Detour:** Removed the experimental 3-node candidate-generation pipeline (`candidate_generation` $\to$ `coverage_comparison` $\to$ `candidate_validation`) from the active production LangGraph workflow. This eliminated production runtime dependence on hardcoded `DOMAIN_CONCEPTS` dictionaries (CS, Physics, Calculus token lists in `apps/ai_classroom/gap_candidates.py`), enabling the system to generalize across any subject or academic domain.
2. **Reconnection & Hardening of LLM Gap Analysis (`gap_detection_node`):** Reconnected the dormant `gap_detection_node` as the primary gap discovery node. Grounded the analysis in the student's note content and retrieved reference material with explicit system guidance, validating outputs against the strict `GAPS_SCHEMA` (`topic`, `why_missing`, `missing_from_note`, `evidence_in_reference`, `source_chunk_ids`).
3. **Optimized Conditional Gap Filling:** Maintained dynamic branching via `_branch_after_gap_detection`: when genuine reference gaps are discovered, `gap_fill_node` generates targeted, reference-grounded explanations; when no reference material or gaps exist, `gap_fill_node` is bypassed directly to citation stitching, saving latency and inference tokens.
4. **Citation Stitching & Provenance Metadata:** Guaranteed that all blocks (both initial draft and gap-fill blocks) stitch reference chunk provenance (`source_title`, `page`, `chapter`, `section`, `chunk_id`, `document_id`) before entering sub-graph lexical evidence verification.
5. **Zero Regressions Across Product Contracts:** Preserved all architectural contracts: `qwen3.5:4b` as production LLM, `Qwen/Qwen3-Embedding-0.6B` (1024-dimension embeddings), shared pgvector hybrid retrieval, Celery asynchronous job dispatch with idempotency, PostgreSQL Row-Level Security (RLS) enforcement across all 28 tables, unprivileged `studyai_app` connection isolation, and atomic persistence.

All 600 backend test cases (592 passed, 8 skipped for SQLite environment constraints), 73 frontend tests, production frontend build, and live PostgreSQL/RLS verification passed with 100% success.

---

## 1. Repository & Branch Baseline

- **Base Branch:** `main` (commit `3252da9`, including Phase 13 reliability fixes)
- **Active Feature Branch:** `feature/phase-14-enrichment-architecture-cleanup`
- **Worktree Status:** Clean, dedicated feature branch
- **Untouched Branches:** `main` remains untouched until PR review and merge

---

## 2. Investigation of Pre-Phase 14 Architecture

Prior to Phase 14, an investigation into the enrichment pipeline revealed:

1. **Disconnected Dead Code:**
   In `backend/ai/langgraph/graphs/enrichment_graph.py`, `gap_detection_node` was imported on line 12 but never added to `StateGraph`. The graph had been modified to branch on `candidate_validation`.
2. **Hardcoded Domain Concepts Coupling:**
   `candidate_generation_node` and `coverage_comparison_node` imported extraction functions from `apps/ai_classroom/gap_candidates.py`. Lines 42–63 of `gap_candidates.py` maintained a hardcoded `DOMAIN_CONCEPTS` set consisting of 63 hardcoded CS, Physics, and Calculus terminology strings. Student notes outside of these narrow keywords suffered degraded gap extraction or noisy n-gram fallbacks.
3. **Over-Engineered Intermediate Stages:**
   Candidate generation split concept identification into three separate stages: deterministic candidate extraction, rule-based coverage classification, and batch LLM validation. This introduced brittle regex matching, sub-phrase noise, and multiple redundant round-trips.
4. **Evaluation Module Roles Clarified:**
   `apps/ai_classroom/gap_candidates.py` and `apps/ai_classroom/gap_candidates_v2.py` serve as historical benchmarks and evaluation test fixtures for golden dataset evaluations (`test_gap_candidates_v2.py`, `test_golden_v2_unit.py`). They must remain intact for benchmark regression testing, but must not be invoked in the production enrichment pipeline.

---

## 3. Simplified Architecture Design & Implementation

### Clean Production Flow

```
[Entry: retrieve]
       │
       ▼
[Node: draft]
       │
       ▼
[Node: gap_detection]
       │
       ├─────────────────────────────────┐
       │ (gaps found)                    │ (no gaps / no reference)
       ▼                                 ▼
[Node: gap_fill]                         │
       │                                 │
       ▼                                 │
[Node: citation_stitch] <────────────────┘
       │
       ▼
[Node: evidence_verification]
       │
       ▼
[Node: format_output]
       │
       ▼
     [END]
```

### Component Implementation Details

1. **`build_enrichment_graph` (`backend/ai/langgraph/graphs/enrichment_graph.py`):**
   - Streamlined graph nodes to 7 distinct stages: `retrieve`, `draft`, `gap_detection`, `gap_fill`, `citation_stitch`, `evidence_verification`, `format_output`.
   - Entry point: `retrieve`.
   - Direct edge: `retrieve` $\to$ `draft` $\to$ `gap_detection`.
   - Conditional edge: `_branch_after_gap_detection` attached to `gap_detection`:
     - Routes to `gap_fill` if `state["gaps_result"]["gaps"]` is non-empty.
     - Routes directly to `citation_stitch` if no gaps are identified.
   - Edges: `gap_fill` $\to$ `citation_stitch` $\to$ `evidence_verification` $\to$ `format_output` $\to$ `END`.

2. **`gap_detection_node` (`backend/apps/ai_classroom/enrichment_nodes.py`):**
   - Grounded directly in `state["evidence_payload"]`.
   - Dynamically checks `evidence_payload["reference_chunks"]`:
     - If reference chunks are present: supplies explicit grounding instruction emphasizing that every gap must be derived from and cite valid chunk IDs from the reference material.
     - If no reference material is present: instructs the model to return empty gaps `{"gaps": []}`, avoiding ungrounded hallucinations.
   - Validates JSON output against `SCHEMAS["gap_detection"]` (`GAPS_SCHEMA`).

3. **`gap_fill_node` (`backend/apps/ai_classroom/enrichment_nodes.py`):**
   - Takes `fill_evidence = {**evidence_payload, "gaps": gaps}`.
   - Generates blocks of type `gap_fill`, citing the specific reference chunk supporting each gap.
   - Validates JSON output against `SCHEMAS["gap_filling"]`.

4. **`citation_stitch_node` (`backend/apps/ai_classroom/enrichment_nodes.py`):**
   - Consolidates `all_blocks = draft_blocks + fill_blocks`.
   - Resolves chunk UUIDs, index labels (`ref_1`, `chunk_1`), and lexical overlap fallbacks against `user_chunks + reference_chunks`.
   - Attaches complete citation metadata (`source_type`, `title`, `page_number`, `page`, `chapter`, `section`, `chunk_id`, `document_id`) to each block.

5. **`_run_verification` (`backend/ai/langgraph/graphs/enrichment_graph.py`):**
   - Sub-graph verification (`invoke_verification_graph`) executing lexical evidence verification between block text and cited chunk content, assigning verification status (`supported`, `partially_supported`, `unsupported`) and score.

6. **`run_enrichment_job` (`backend/apps/ai_classroom/services.py`):**
   - Records execution checkpoint in `JobExecutionState`.
   - Executes atomic transaction:
     - Supersedes older non-stale `EnrichedNote` instances for the document.
     - Creates new `EnrichedNote` with content hash, revision IDs, provider, and model.
     - Creates `EnrichedNoteBlock` for each block in order.
     - Creates `CitationBlock` linking source references and verifier scores.
     - Triggers document tagging and question generation hooks within the atomic boundary.

---

## 4. Verification Evidence & Test Results

### 4.1. Unit & Graph Tests (`test_enrichment_graph.py`)

- **Command:** `docker exec studyai-api-1 pytest tests/unit/test_enrichment_graph.py --ds=config.settings.test`
- **Result:** **13 passed, 0 failed** in 1.64s
- **Verified Areas:**
  - `test_retrieve_node_returns_chunks`
  - `test_draft_node_returns_blocks`
  - `test_gap_detection_node_returns_gaps`
  - `test_gap_fill_node_skips_when_no_gaps`
  - `test_citation_stitch_node_stitches_refs`
  - `test_evidence_verification_node_classifies`
  - `test_format_output_node_passthrough`
  - `test_graph_builds_successfully`
  - `test_branch_after_gap_detection_with_gaps`
  - `test_branch_after_gap_detection_without_gaps`
  - `test_branch_after_gap_detection_empty_gaps_result`
  - `test_full_pipeline_with_gaps_e2e` (New Phase 14 E2E test)
  - `test_full_pipeline_without_gaps_e2e` (New Phase 14 E2E test)

### 4.2. API & Integration Tests (`test_ai_classroom.py`)

- **Command:** `docker exec studyai-api-1 pytest tests/api/test_ai_classroom.py --ds=config.settings.test`
- **Result:** **9 passed, 0 failed** in 1.79s
- **Verified Areas:**
  - Full pipeline over indexed document creates verified note
  - Subsequent enrich requests return existing note (coalescing)
  - User edits correctly mark enrichment as `ai_stale`
  - Citation blocks contain valid verifier status and chunk references

### 4.3. Evaluation Benchmark Tests (`tests/evaluation/`)

- **Command:** `docker exec studyai-api-1 pytest tests/evaluation/ --ds=config.settings.test`
- **Result:** **20 passed, 0 failed** in 10.29s
- **Verified Areas:**
  - Golden v2 dataset unit tests and schema integrity
  - Isolation and quality constraints in evaluator modules

### 4.4. Full Backend Regression Test Suite

- **Command:** `docker exec studyai-api-1 pytest --ds=config.settings.test -rs`
- **Result:** **592 passed, 8 skipped, 0 failed** across 600 collected items in 35.11s
- **Skipped Test Audit (8 skips expected under SQLite test environment):**
  1. `tests/api/test_phase12_security.py:285` (RLS transaction binding requires PostgreSQL)
  2. `tests/api/test_retrieval.py:283` (Dense channel requires pgvector PostgreSQL)
  3. `tests/unit/test_shared.py:20` (RLS context requires PostgreSQL)
  4. `tests/unit/test_shared.py:37` (RLS context requires PostgreSQL)
  5. `providers/tests/test_ocr.py:105` (Tesseract system library in test container)
  6. `providers/tests/test_ocr.py:121` (Tesseract system library in test container)
  7. `providers/tests/test_ocr.py:141` (PaddleOCR optional provider)
  8. `providers/tests/test_ocr.py:153` (PaddleOCR optional provider)

### 4.5. Frontend Unit Tests & Build

- **Command:** `npm run test` (Vitest)
- **Result:** **11 test files passed, 73 tests passed (100%)** in 680ms
- **Command:** `npm run build` (`tsc -b && vite build`)
- **Result:** Production bundle built cleanly with zero TypeScript errors.

### 4.6. Live PostgreSQL & RLS Stack Verification

Executed live verification script in running containers with production PostgreSQL and pgvector:
1. Created user, active profile, and subject under RLS transaction context (`profile_scoped_transaction`).
2. Ingested and indexed a reference textbook document on Graph Algorithms (`Dijkstra's Algorithm`, page 658) with `Qwen/Qwen3-Embedding-0.6B` vectors.
3. Created student note document with handwriting OCR revisions and indexed chunks.
4. Enqueued and ran enrichment job through `invoke_enrichment_graph`.
5. Confirmed `EnrichedNote` created with atomic blocks:
   - Overview block generated and stitched with citations
   - Key concept blocks generated and verified
   - Citation blocks verified with status (`supported`) and valid page numbers
6. Confirmed profile isolation: secondary user profile access rejected with `ResourceNotFound`.

---

## 5. Summary of Files Changed

| File | Change Description |
|---|---|
| `backend/ai/langgraph/graphs/enrichment_graph.py` | Replaced 3 candidate-generation nodes (`candidate_generation`, `coverage_comparison`, `candidate_validation`) with direct `gap_detection` node; attached conditional edge `_branch_after_gap_detection` to `gap_detection`. |
| `backend/apps/ai_classroom/enrichment_nodes.py` | Added dynamic grounding instructions to `gap_detection_node`; documented legacy candidate extraction nodes as deprecated/superseded. |
| `backend/tests/unit/test_enrichment_graph.py` | Updated `MockLLMProvider` schema compliance for `gap_detection`; added `test_full_pipeline_with_gaps_e2e` and `test_full_pipeline_without_gaps_e2e` integration tests. |
| `docs/product/phase14_enrichment_architecture_cleanup.md` | Comprehensive Phase 14 architecture report and verification documentation. |
