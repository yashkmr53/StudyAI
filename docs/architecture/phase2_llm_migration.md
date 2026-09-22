# Phase 2 — LLM Stack Migration: Canonical `qwen3.5:4b` Implementation

**Date:** September 21, 2026  
**Status:** Completed & Verified  
**Canonical LLM:** `qwen3.5:4b` (via native host Ollama with Apple Silicon GPU acceleration)  
**Embeddings:** `Qwen/Qwen3-Embedding-0.6B` (Target for Phase 3)  
**Production Fallbacks:** Completely Disabled (`LLM_DISABLE_FALLBACK=1`)

---

## 1. Executive Summary

Phase 2 replaced the legacy fragmented LLM setup (which had partial implementations, hardcoded fallbacks, and Docker CPU emulation) with a unified, high-performance canonical provider: [`Qwen35Provider`](backend/providers/llm/qwen35.py).

All four fundamental generative AI modalities required for StudyAI are now implemented and operational:
1. **Plain Text Generation:** Conversational tutoring, explanations, and agent responses.
2. **Structured Output Generation:** Pydantic model and JSON schema validation with retry loop.
3. **Multimodal Vision:** Handwritten note OCR and image inspection.
4. **Multimodal Structured Extraction:** Extracting structured transcription and tabular data directly from images.

---

## 2. Key Architecture Decisions & Changes

### 2.1 Native Host Execution with GPU Acceleration
* **Problem:** In Docker Desktop on macOS, Linux containers cannot access Apple Silicon Metal GPU acceleration without heavy virtualization penalties. When running in a container, Ollama ran on 100% CPU, generating at only ~6 tokens/second and timing out on complex reasoning tasks.
* **Solution:**
  - Removed the `ollama` container and its associated `ollama_data` volume from [`docker-compose.yml`](docker-compose.yml).
  - Deleted the `studyai-ollama-1` container.
  - StudyAI connects to the host's native Ollama service (`/usr/local/bin/ollama`) at `http://localhost:11434` (or `http://host.docker.internal:11434` from containerized services).
  - Native host execution runs at **100% GPU (Apple Silicon unified memory Metal)**, delivering fast generation and native multimodal vision throughput.

### 2.2 Token Window Sizing (`num_predict=4096`, `num_ctx=16384`)
* **Problem:** `qwen3.5:4b` has native reasoning/thinking capabilities. Small token limits (such as 100 or 256) hit `done_reason: length` before the model finished thinking, leaving `message.content` completely empty.
* **Solution:**
  - Defaulted `LLM_NUM_PREDICT=4096` and `LLM_NUM_CTX=16384` across [`.env`](.env), [`.env.example`](.env.example), and [`backend/config/settings/base.py`](backend/config/settings/base.py).
  - This ensures sufficient room for reasoning while ensuring the model generates its complete final response in `content`.

### 2.3 Strict Content Output (No Thinking Artifacts)
* **Problem:** When reasoning models generate thinking traces, internal monologue can pollute application output if not cleanly separated.
* **Solution:**
  - Output is extracted strictly from `message.content` (or structured parsed Pydantic objects).
  - No thinking texts are presented to users or passed down the pipeline.

### 2.4 Granular Stage-Based Thinking Configuration
* **Problem:** Thinking is computationally valuable for complex gap detection and enrichment synthesis, but adds unnecessary latency to high-speed transcription (OCR), tagging, or simple chat.
* **Solution:**
  - Added stage-specific environment flags to [`.env`](.env) and [`backend/config/settings/base.py`](backend/config/settings/base.py):
    ```bash
    LLM_THINK_DEFAULT=0
    LLM_THINK_OCR=0
    LLM_THINK_ENRICHMENT=1
    LLM_THINK_GAP_DETECTION=1
    LLM_THINK_QUESTION_GEN=0
    LLM_THINK_CHAT=0
    LLM_THINK_TAGGING=0
    LLM_THINK_VERIFICATION=1
    ```
  - [`Qwen35Provider._resolve_think()`](backend/providers/llm/qwen35.py) automatically resolves the thinking flag based on prompt name, while allowing callers to override via `think=True` or `think=False`.

### 2.5 Structured Output with Retry Loop
* **Problem:** Occasional JSON formatting inconsistencies or schema validation mismatches can occur on edge-case generations.
* **Solution:**
  - [`Qwen35Provider.generate_structured()`](backend/providers/llm/qwen35.py) and `generate_structured_with_image()` use `ChatOllama`'s `with_structured_output` wrapped in a robust `try...except` retry loop (up to `max_retries = 2`, totaling 3 attempts).
  - Catches validation and parse errors, retrying automatically before raising a `RuntimeError`.

### 2.6 Zero Production Fallback (Rule 5 Enforcement)
* **Problem:** Previous versions allowed silent fallback to `MockLLMProvider` when Ollama failed, hiding production failures.
* **Solution:**
  - In [`backend/providers/registry.py`](backend/providers/registry.py), `LLM_PROVIDER=ollama` enforces `disable_fallback=True` on [`LLMChainProvider`](backend/providers/llm/chain.py).
  - Failures in production immediately raise `ProviderError` with full provenance, ensuring problems are never hidden behind synthetic mocks.

---

## 3. Implementation Details

### Modified & Created Files

| File | Purpose |
| :--- | :--- |
| [`backend/providers/llm/qwen35.py`](backend/providers/llm/qwen35.py) | Canonical `Qwen35Provider` using `ChatOllama`, stage thinking resolution, retry loop, and multimodal vision. |
| [`backend/providers/base.py`](backend/providers/base.py) | Updated `LLMProvider` protocol and `LLMResult` / `StructuredLLMResult` dataclasses with `latency_ms`. |
| [`backend/providers/llm/__init__.py`](backend/providers/llm/__init__.py) | Exported `Qwen35Provider`. |
| [`backend/providers/llm/chain.py`](backend/providers/llm/chain.py) | Forwarded kwargs, supported positional/keyword prompts, and enforced `disable_fallback`. |
| [`backend/providers/llm/mock.py`](backend/providers/llm/mock.py) | Updated mock to support all 4 protocol methods for isolated unit tests. |
| [`backend/providers/registry.py`](backend/providers/registry.py) | Routes `ollama` and `qwen3.5:4b` exclusively to `Qwen35Provider`, removes legacy hosted models, enforces zero fallback. |
| [`backend/config/settings/base.py`](backend/config/settings/base.py) | Defaults for `LLM_NUM_CTX=16384`, `LLM_NUM_PREDICT=4096`, and per-stage thinking settings. |
| [`backend/config/settings/test.py`](backend/config/settings/test.py) | Configured deterministic mock provider for isolated unit test runs. |
| [`docker-compose.yml`](docker-compose.yml) | Removed Ollama container; added host-gateway route to native host Ollama. |
| [`.env`](.env) & [`.env.example`](.env.example) | Configured host Ollama endpoint, model name, and stage thinking flags. |
| [`backend/providers/tests/test_qwen35.py`](backend/providers/tests/test_qwen35.py) | Unit test suite covering provenance, stage thinking, plain text, structured Pydantic, retry loops, multimodal vision, and registry resolution. |

---

## 4. Verification Results

### 4.1 Live GPU End-to-End Tests (Native `qwen3.5:4b`)

All 4 operations were verified live against native `qwen3.5:4b` on Apple Silicon GPU (`100% GPU`):

```text
Provider Chain: LLMChainProvider disable_fallback: True
Primary: Qwen35Provider model: qwen3.5:4b base_url: http://localhost:11434
num_ctx: 16384 num_predict: 4096

1. Plain Text:
   Output: "Welcome to StudyAI"
   Model: qwen3.5:4b | Status: Verified

2. Structured Generation (Pydantic Schema):
   Output: {'tags': ['Metabolism', 'Energy Production', 'Mitochondria']}
   Model: qwen3.5:4b | Status: Verified

3. Multimodal Text (Image Input):
   Output: "The image is entirely black; there are no visible objects, text, or details."
   Model: qwen3.5:4b | Status: Verified

4. Multimodal Structured Generation:
   Output: {'is_blank': True, 'summary': 'The image is completely black and contains no visual content.'}
   Model: qwen3.5:4b | Status: Verified

Stage Thinking Resolution:
   - ocr: False
   - enrichment: True
   - enrichment (explicit False override): False
```

### 4.2 Automated Test Suites

1. **Qwen35 Provider Unit Tests:**
   `pytest backend/providers/tests/test_qwen35.py --ds=config.settings.test`
   **Result:** 9 passed in 1.29s (100%).

2. **Full Provider Test Suite:**
   `pytest backend/providers/tests/ --ds=config.settings.test`
   **Result:** 138 passed, 4 skipped in 24.14s (100%).

3. **Backend Unit Test Suite:**
   `pytest backend/tests/unit/ --ds=config.settings.test`
   **Result:** 145 passed, 2 skipped in 1.70s (100%).

---

## 5. Next Phase: Phase 3 — Migrate the Embedding Stack

With the LLM stack cleanly migrated to native `qwen3.5:4b`:
- **Current Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
- **Target Embeddings:** `Qwen/Qwen3-Embedding-0.6B`.
- **Key Tasks in Phase 3:**
  1. Audit existing embedding models, vector dimensions, and pgvector schema definitions.
  2. Implement `Qwen3EmbeddingProvider` wrapping `Qwen/Qwen3-Embedding-0.6B`.
  3. Determine target vector dimension and migration path for pgvector tables.
  4. Ensure hybrid retrieval and RRF fusion operate with the new embedding dimension.
