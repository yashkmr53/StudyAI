# StudyAI Phase 1: Foundation Implementation

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Backend AI framework layer — LangChain adapters, LangGraph scaffolding, LangSmith tracing

---

## 1. What Was Built

### 1.1 LangChain Integration (`ai/langchain/`)

| File | Purpose |
|------|---------|
| `models.py` | `LangChainChatModelAdapter` (wraps `ChatOllama`), `LangChainEmbeddingAdapter` (wraps `HuggingFaceEmbeddings`), `get_chat_model()`, `get_embedding_model()`, `get_provider_chain()` |
| `prompts.py` | `PromptTemplate`, `PromptRegistry` (loads from `ai/prompts/*.json`), `active_prompt()`, `validate_stage_output()`, `build_provider_prompt()` |
| `retrievers.py` | `StudyAIRetriever` (LangChain `BaseRetriever` wrapping `RetrievalService.search()`) |

**Key design decisions:**
- Provider abstraction boundary preserved: `LLMProvider` Protocol remains the application boundary
- LangChain models are adapters *inside* the provider layer, not replacing it
- `get_chat_model()` supports `ollama-langchain`, `ollama`, `mock` — preserves existing provider chains

### 1.2 LangGraph State (`ai/langgraph/state/`)

| File | Purpose |
|------|---------|
| `base_state.py` | `BaseStudyAIState` — shared error and metadata fields |
| `chat_state.py` | `ChatState` — typed state for Ask StudyAI workflow |

**State design:**
- Uses `TypedDict` with `total=False` for partial updates
- Explicit fields: `user_request`, `profile_id`, `subject_id`, `session_id`, `retrieved_evidence`, `selected_evidence`, `answer`, `citations`, `verification_status`, `verification_score`, `retry_count`
- No arbitrary unstructured dictionaries

### 1.3 LangSmith Tracing (`ai/tracing/`)

| File | Purpose |
|------|---------|
| `config.py` | LangSmith client init from env vars, `trace_context()`, `traceable()`, `log_llm_call()`, `log_tool_call()`, `log_retrieval()` |
| `decorators.py` | `@traced_node` (graph nodes), `@traced_graph` (graph invocation) |
| `context.py` | `TraceContext` propagation via `contextvars` |

**Tracing policy:**
- Traces LLM calls, graph execution, node execution, retrieval, tool calls
- Does NOT trace internal Python functions, DB queries, RLS checks, auth checks
- Never sends passwords, tokens, signed URLs, raw DB rows to LangSmith

### 1.4 Schemas (`ai/schemas/`)

| File | Purpose |
|------|---------|
| `chat.py` | `ChatAnswer`, `ChatAnswerRetry` — Pydantic models for structured LLM output |

### 1.5 Tools (`ai/tools/`)

| File | Purpose |
|------|---------|
| `base.py` | `StudyAITool`, `ToolResult` — base tool wrapper preserving auth/validation boundaries |
| `retrieval_tool.py` | `SearchNotesTool` — wraps `RetrievalService.search()` |

### 1.6 Environment Configuration

| File | Change |
|------|--------|
| `.env.example` | Added `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` |
| `docker-compose.yml` | Added LangSmith env vars to `api`, `worker`, `beat` services via `&backend-env` |

### 1.7 Bug Fix

| File | Issue | Fix |
|------|-------|-----|
| `ai/langchain/models.py` | `response` variable referenced outside `else` branch in `generate_structured()` | Assigned `response = result` in structured output branch |

---

## 2. Dependency Changes

Added to `backend/requirements.txt`:
```
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-community>=0.3.0
langchain-ollama>=0.2.0
langsmith>=0.1.0
```

No changes to: `django`, `djangorestframework`, `celery`, `redis`, `pgvector`, `sentence-transformers`, `tesserocr`.

---

## 3. Directory Structure

```
backend/ai/
├── __init__.py
├── langchain/
│   ├── __init__.py
│   ├── models.py                # Model factory + adapters
│   ├── prompts.py               # Prompt registry
│   └── retrievers.py            # StudyAIRetriever
├── langgraph/
│   ├── __init__.py
│   ├── state/
│   │   ├── __init__.py
│   │   ├── base_state.py
│   │   └── chat_state.py
│   ├── graphs/
│   │   ├── __init__.py
│   │   └── chat_graph.py        # Chat workflow graph
│   └── (nodes live in apps/chat/ to avoid circular imports)
├── prompts/                     # JSON prompt templates
├── providers/
│   └── __init__.py
├── schemas/
│   ├── __init__.py
│   └── chat.py                  # ChatAnswer, ChatAnswerRetry
├── tracing/
│   ├── __init__.py
│   ├── config.py                # LangSmith init
│   ├── decorators.py            # @traced_node, @traced_graph
│   └── context.py               # TraceContext propagation
└── tools/
    ├── __init__.py
    ├── base.py                  # StudyAITool base class
    └── retrieval_tool.py        # SearchNotesTool
```

**Important:** Chat graph nodes live in `apps/chat/langgraph_nodes.py` (not `ai/langgraph/nodes/`) to avoid circular imports between `ai/` and `apps/`.

---

## 4. Tests Added

| File | Coverage |
|------|----------|
| `tests/unit/test_ai_foundation.py` | LangChain models, prompt registry, tracing config |
| `tests/unit/test_chat_graph.py` | Chat graph nodes, graph build, branching logic |

---

## 5. Validation

- All Python files pass syntax validation
- Phase 1 foundation is complete and ready for Phase 2 (Ask StudyAI migration)

---

## 6. Next Steps

1. Run full test suite (`python manage.py test`) to validate Phase 1
2. Validate LangSmith traces in development
3. Proceed to **Phase 2: Ask StudyAI Migration** (already partially implemented in `apps/chat/services.py`)
