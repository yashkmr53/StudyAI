# StudyAI Architecture Audit — Phase 0: LangGraph/LangChain/LangSmith Migration

**Date:** 2026-08-24  
**Status:** Audit Complete — Ready for Approval  
**Scope:** Backend AI layer (Django + Celery + PostgreSQL + pgvector + local providers)

---

## 1. Architecture Audit Summary

### Current State Assessment

| Area | Status | Notes |
|------|--------|-------|
| **Provider Abstraction** | ✅ Mature | LLM, Embedding, OCR, Storage, Email — all behind Protocol interfaces with fallback chains |
| **Observability** | ✅ Partial | `ProviderCallLog` (DB) + structured logging; no distributed tracing |
| **AI Workflows** | ⚠️ Ad-hoc | Sequential functions in services; custom agent loop in `AgentOrchestrator` |
| **Evaluation** | ✅ Framework exists | Retrieval, Citation, Agent metrics runners; datasets need population |
| **Security/Guardrails** | ✅ Strong | Prompt injection directive, data minimization, RLS, tool auth, budget enforcement |
| **LangChain/LangGraph/LangSmith** | ❌ Not used | Architecture explicitly deferred them (see `docs/phase_6/architecture/ASSUMPTIONS_AND_DECISIONS.md`) |

### Key Architectural Decisions Already Made

1. **Provider abstraction is the application boundary** — model integrations are adapters, not direct SDK usage
2. **PostgreSQL + pgvector is the retrieval substrate** — no external vector DB
3. **Celery + Redis is the job queue** — DB is source of truth; Redis is broker only
4. **Local-first providers** — Ollama (LLM), sentence-transformers (embeddings), Tesseract (OCR)
5. **Schema-validated LLM outputs** — Pydantic + JSON schema at every step
6. **Incremental, revision-aware indexing** — content-hash deduplication, stale propagation
7. **Evidence verifier is deterministic rule-based code** — not an LLM call
8. **Agent tools call domain services** — not raw DB/SQL

---

## 2. Current AI Execution Paths

### 2.1 LLM Invocation Points

| Location | Purpose | Provider Path |
|----------|---------|---------------|
| `apps/chat/services.py:69` | Classic chat RAG answer | `LLMChainProvider` → `OllamaLLMProvider`/`MockLLMProvider` |
| `apps/agents/services/orchestrator.py:184` | Agent orchestrator decisions | Same chain |
| `apps/ai_classroom/services.py:264` | Enrichment draft | Same chain |
| `apps/ai_classroom/services.py:276` | Gap detection | Same chain |
| `apps/ai_classroom/services.py:289` | Gap filling | Same chain |
| `apps/questions/services.py:64` | MCQ generation | Same chain |

**Pattern:** All use `providers.registry.get_llm_provider()` → `LLMChainProvider.generate_structured(Prompt, schema, request_id)`

### 2.2 Embedding Generation Points

| Location | Purpose |
|----------|---------|
| `apps/retrieval/services.py:230` | Index new/changed chunks during `run_index_job` |
| `apps/retrieval/services.py:235` | Store `embedding_model` and `embedding_version` per chunk |

**Pattern:** `providers.registry.get_embedding_provider().embed(texts, model_version=...)`

### 2.3 OCR Invocation Points

| Location | Purpose |
|----------|---------|
| `apps/documents/services.py:208` | `OCRChainProvider.recognize(image_uri, request_id)` in `run_ocr_job` |

### 2.4 Retrieval Execution Points

| Location | Purpose |
|----------|---------|
| `apps/retrieval/retrieval.py:RetrievalService.search()` | Hybrid dense + keyword + RRF, profile/subject scoped |
| Called from: `chat/services.py`, `agents/tools/learning.py`, `questions/services.py` (indirect), `evaluation/runner.py` |

### 2.5 Prompt Construction

| Location | Pattern |
|----------|---------|
| `apps/ai_classroom/prompts.py` | `active_prompt(stage)` returns `PromptTemplate` with `template`, `version`, `output_schema_version` |
| `apps/chat/services.py` | Inline JSON payload construction |
| `apps/agents/prompts/agent_prompts.py` | `build_agent_system_prompt()` with tool descriptions |
| `apps/questions/services.py` | Inline evidence JSON |

### 2.6 Structured Output Parsing

| Location | Pattern |
|----------|---------|
| `providers/llm/local.py` | `format=json` + schema in system prompt → `json.loads(response)` with fallback extraction |
| `providers/llm/chain.py` | Sanitization + prompt injection directive prepended |
| Validation: `apps/ai_classroom/prompts.py:validate_stage_output()` uses `jsonschema` |

### 2.7 AI Workflow Orchestration

| Workflow | Current Implementation |
|----------|------------------------|
| **Chat (classic)** | `ChatService._ask_classic()` — linear: retrieve → LLM → verify → persist |
| **Chat (agent)** | `AgentOrchestrator.run()` — custom loop: LLM decision → tool → observe → repeat |
| **Enrichment** | `run_enrichment_job()` — linear stages A→B→C→D→E→F with schema validation per stage |
| **Question Generation** | `QuestionGenerationService.generate_for_document()` — per-chunk LMC call + dedup |
| **Revision Planning** | `RevisionPlanningService.build_plan()` — pure deterministic SQL/python, no LLM |
| **OCR + Index** | Celery jobs: `run_ocr_job` → `run_index_job` (chained) |

### 2.8 Validation/Verification

| Component | Type |
|-----------|------|
| `EvidenceVerifier` | Lexical overlap (deterministic, rule-based) |
| `validate_stage_output()` | JSON Schema validation (enrichment draft/gaps/fill) |
| Pydantic models | Tool input/output schemas |
| `PromptVersion` tracking | `prompt_version` stored on every AI artifact |

### 2.9 Existing Celery AI Jobs

| Job Type | Handler | Trigger |
|----------|---------|---------|
| `ocr` | `run_ocr_job` | Document upload finalization |
| `index` | `run_index_job` | Post-OCR, post-user-edit, manual |
| `enrich` | `run_enrichment_job` | Manual or auto after indexing |
| `pdf_render` | `NoteSpaceService.render_and_store` | Manual export |

### 2.10 Current Observability/Telemetry

| Mechanism | Scope |
|-----------|-------|
| `ProviderCallLog` (DB) | Every LLM/OCR/Embedding provider call: latency, tokens, cost, success/error, metadata |
| Structured logging | Request-ID correlated, includes provider, model, latency |
| `AgentExecutionLog` (DB) | Agent runs: intent, tools, iterations, tokens, verification |
| `EvalRun` (DB) | Evaluation harness results |
| Prometheus metrics | `/metrics` endpoint (disabled by default) |

### 2.11 Existing Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/api/test_ai_classroom.py` | Enrichment API |
| `backend/tests/api/test_chat.py` | Chat endpoints |
| `backend/tests/api/test_retrieval.py` | Retrieval search |
| `backend/tests/integration/test_agents.py` | Agent orchestration |
| `backend/providers/tests/test_llm.py` | Provider chain, mock, Ollama |
| `backend/providers/tests/test_embeddings.py` | Embedding providers |
| `backend/providers/tests/test_ocr.py` | OCR providers |
| `backend/apps/agents/tests/` | Tool registry, individual tools |
| `backend/apps/evaluation/runner.py` | Evaluation metrics (retrieval, citation, agent) |

---

## 3. LangGraph/LangChain Migration Boundaries

### 3.1 Where LangGraph Adds Value (Adopt)

| Workflow | Reason |
|----------|--------|
| **Ask StudyAI (Chat)** | Multi-step: retrieval → evidence selection → answer → citation verification; branching on verification failure; retries |
| **AI Enrichment** | 6-stage pipeline with validation loops; gap detection → gap fill is conditional branching; retry on verification failure |
| **Question Generation** | Retrieve source + reference → generate → validate → verify → persist; can branch on difficulty validation |
| **Adaptive Tests** | Mastery → weak topics → retrieve → generate → verify → create test; iterative |
| **Revision Planning (future agentic)** | Get mastery → identify weak → search notes → search refs → generate → verify → schedule |
| **Agentic workflows** | Tool selection, loops, branching, human-in-the-loop (future) |

### 3.2 Where LangChain Adds Value (Adopt Selectively)

| Primitive | Current Implementation | LangChain Replacement |
|-----------|------------------------|----------------------|
| **ChatModel abstraction** | `LLMProvider` Protocol + `OllamaLLMProvider` | `ChatOllama` + custom adapter preserving provider interface |
| **Prompt templates** | Raw strings + `Prompt` dataclass + `PromptTemplate` class in `ai_classroom/prompts.py` | `PromptTemplate`, `ChatPromptTemplate`, `MessagesPlaceholder` |
| **Structured output** | JSON schema in system prompt + `json.loads` + fallback extraction | `with_structured_output()` / `JsonOutputParser` + Pydantic |
| **Tool abstraction** | Custom `BaseTool` + `ToolRegistry` | `@tool` decorator + `Tool` class (but keep our auth/validation wrapper) |
| **Retriever interface** | `RetrievalService.search()` returning custom `Evidence` objects | `BaseRetriever` implementation wrapping our service |
| **Message handling** | Manual conversation list management | `BaseMessage`, `AIMessage`, `HumanMessage`, `SystemMessage` |

### 3.3 Where NOT to Introduce LangChain/LangGraph

| Component | Reason |
|-----------|--------|
| **Provider abstraction layer** | Already clean; LangChain model integrations go *behind* it, not replace it |
| **Celery job infrastructure** | Job queue, retries, idempotency, RLS context — battle-tested |
| **PostgreSQL retrieval (pgvector + tsvector + RRF)** | Highly tuned, revision-aware, incremental — no benefit from LangChain retrievers |
| **EvidenceVerifier** | Deterministic rule-based; LLM-based verification adds latency/cost without clear gain |
| **RevisionPlanningService** | Pure deterministic logic; no LLM involved |
| **OCR pipeline** | Image → text; no orchestration benefit |
| **Document ingestion/chunking** | Deterministic, revision-aware, incremental |
| **Budget enforcement** | Simple counter; no orchestration needed |
| **Simple single-shot LLM calls** | e.g., one-off classification — overhead not justified |

---

## 4. LangSmith Integration Plan

### 4.1 Configuration

Environment variables (backend only — never frontend, never git, never Docker image layers):

```bash
LANGSMITH_API_KEY=<set in deployment secrets>
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=studyai
```

**Docker Compose:** Add to `api`, `worker`, `beat` services via `.env` (not in `docker-compose.yml` directly).

### 4.2 Tracing Policy

| Trace | LangSmith Run Name | Metadata |
|-------|-------------------|----------|
| Chat (classic) | `studyai.chat.classic` | `profile_id`, `subject_id`, `session_id`, `model`, `prompt_version`, `retrieval_k` |
| Chat (agent) | `studyai.chat.agent` | Same + `iterations`, `tool_calls` |
| Enrichment | `studyai.enrichment` | `document_id`, `profile_id`, `revision_ids`, `prompt_versions`, `blocks_count` |
| Question Generation | `studyai.question_generation` | `document_id`, `profile_id`, `questions_generated` |
| Adaptive Test | `studyai.adaptive_test` | `profile_id`, `subject_id`, `weak_topics`, `question_count` |
| Revision Plan | `studyai.revision_plan` | `profile_id`, `subject_id`, `horizon_days` |
| Agent Tool Call | `studyai.agent.tool.{tool_name}` | `tool`, `arguments`, `latency_ms`, `success` |
| Retrieval | `studyai.retrieval` | `query_hash`, `profile_id`, `subject_id`, `k`, `results_count`, `latency_ms` |
| LLM Call | `studyai.llm.{prompt_name}` | `model`, `provider`, `prompt_version`, `tokens`, `latency_ms` |
| Evaluation | `studyai.eval.{kind}` | `dataset`, `cases`, `metrics` |

**Do NOT trace:** Internal Python functions, DB queries, RLS checks, budget checks, auth checks.

**Do NOT send to LangSmith:** Passwords, tokens, signed URLs, raw DB rows, private note content beyond what's in the LLM context.

### 4.3 Implementation Approach

1. **Phase 1 Foundation:** Create `backend/ai/tracing/` with LangSmith client initialization, context managers, decorators
2. **Per-feature:** Wrap graph execution, node execution, LLM calls, tool calls, retrieval
3. **Use `@traceable`** on graph nodes and key functions
4. **Pass `run_id`/`trace_id`** through request context for correlation

---

## 5. Provider Abstraction Strategy

### 5.1 Principle

**Provider abstraction remains the application boundary.** LangChain model integrations are adapters *inside* the provider implementation.

```
StudyAI Code
      ↓
Provider Interface (LLMProvider Protocol)
      ↓
LangChain Adapter (internal)
      ↓
Ollama / OpenAI / Anthropic / etc.
```

### 5.2 Changes Required

1. **Create `OllamaLangChainAdapter`** implementing `LLMProvider` using `ChatOllama`
2. **Preserve `LLMChainProvider`** fallback logic — it wraps providers, not LangChain directly
3. **Keep `Prompt` dataclass** as application-level prompt representation
4. **Keep `StructuredLLMResult`** as application-level result
5. **Embedding provider**: Create `SentenceTransformerLangChainAdapter` if needed (sentence-transformers not in LangChain core)
6. **OCR provider**: No change — LangChain has no OCR abstraction

### 5.3 Migration Path

- **Step 1:** Add LangChain adapter alongside existing `OllamaLLMProvider`
- **Step 2:** Switch `LLM_PROVIDER_CHAIN=ollama-langchain,mock` in staging
- **Step 3:** Validate behavior equivalence (same outputs, same telemetry)
- **Step 4:** Deprecate raw `OllamaLLMProvider` (keep for reference)

---

## 6. Proposed Directory Structure

```
backend/
  ai/
    __init__.py
    langgraph/
      __init__.py
      graphs/
        chat_graph.py
        enrichment_graph.py
        question_generation_graph.py
        citation_verification_graph.py
        adaptive_test_graph.py
        revision_planning_graph.py
      state/
        __init__.py
        chat_state.py
        enrichment_state.py
        question_state.py
        base_state.py
      nodes/
        __init__.py
        retrieval_node.py
        evidence_selection_node.py
        answer_generation_node.py
        citation_verification_node.py
        draft_node.py
        gap_detection_node.py
        gap_fill_node.py
        question_generation_node.py
        difficulty_validation_node.py
      checkpointer.py          # Optional: PostgresSaver for persistence
    langchain/
      __init__.py
      models.py                # Model factory: get_chat_model(), get_embedding_model()
      prompts.py               # PromptTemplate registry, version management
      structured_output.py     # Pydantic schemas + output parsers
      retrievers.py            # StudyAIRetriever (BaseRetriever impl)
      tools/
        __init__.py
        base.py                # Tool wrapper preserving auth/validation
        retrieval_tool.py
        evidence_tool.py
        learning_tools.py      # Wrappers for existing learning tools
    tracing/
      __init__.py
      config.py                # LangSmith init from env
      decorators.py            # @traceable, @traced_node
      context.py               # run_id propagation
    providers/
      __init__.py
      ollama_adapter.py        # ChatOllama → LLMProvider
      sentence_transformer_adapter.py  # → EmbeddingProvider
    schemas/
      __init__.py
      chat.py
      enrichment.py
      questions.py
      citations.py
      agent.py
```

**Integration with existing apps:**
- `apps/chat/services.py` → imports `ai.langgraph.graphs.chat_graph`
- `apps/ai_classroom/services.py` → imports `ai.langgraph.graphs.enrichment_graph`
- `apps/questions/services.py` → imports `ai.langgraph.graphs.question_generation_graph`
- `apps/agents/` → uses `ai.langchain.tools` + `ai.langgraph` for new agentic workflows

---

## 7. Feature-by-Feature Migration Plan

### Phase 1: Foundation (Week 1-2)
- [ ] Add `langchain`, `langgraph`, `langsmith` to requirements
- [ ] Create `backend/ai/` directory structure
- [ ] Implement LangSmith configuration (`ai/tracing/config.py`)
- [ ] Create model factory (`ai/langchain/models.py`) with Ollama adapter
- [ ] Create prompt registry (`ai/langchain/prompts.py`) migrating from `ai_classroom/prompts.py`
- [ ] Create structured output schemas (`ai/schemas/`)
- [ ] Create `StudyAIRetriever` (`ai/langchain/retrievers.py`)
- [ ] Add LangSmith env vars to `.env.example` and Docker Compose (api/worker/beat)
- [ ] Unit tests for foundation components

### Phase 2: Ask StudyAI Migration (Week 2-3)
- [ ] Define `ChatState` (`ai/langgraph/state/chat_state.py`)
- [ ] Implement graph nodes: retrieval → evidence selection → answer generation → citation verification
- [ ] Build `chat_graph.py` with proper edges, retries, branching
- [ ] Integrate with `ChatService.ask()` — swap `_ask_classic` for graph invocation
- [ ] Add LangSmith tracing to all nodes
- [ ] Run existing chat tests + new graph tests
- [ ] Validate LangSmith traces in UI

### Phase 3: AI Enrichment Migration (Week 3-4)
- [ ] Define `EnrichmentState`
- [ ] Implement nodes for each stage: retrieve, draft, gap detection, gap fill, citation stitch, verification
- [ ] Build `enrichment_graph.py` with conditional edges (gap detection → gap fill)
- [ ] Integrate with `run_enrichment_job()` — replace linear function calls
- [ ] Preserve: `PromptVersion`, `EvidenceVerifier`, staleness propagation, coalescing
- [ ] Add tracing
- [ ] Run enrichment tests

### Phase 4: Question Generation Migration (Week 4-5)
- [ ] Define `QuestionGenerationState`
- [ ] Graph: retrieve source → retrieve reference → generate → validate → verify → persist
- [ ] Integrate with `QuestionGenerationService`
- [ ] Add difficulty validation node (branch on failure)
- [ ] Tracing
- [ ] Tests

### Phase 5: Citation/Evidence Verification Graph (Week 5)
- [ ] Extract verification into reusable graph/node
- [ ] Use as sub-graph in chat, enrichment, question generation
- [ ] Tracing

### Phase 6: Adaptive Tests (Week 5-6)
- [ ] Graph: get mastery → identify weak → retrieve → generate → verify → create test
- [ ] Integrate with `TestGenerationService` / agent tools

### Phase 7: Revision Planning (Week 6)
- [ ] Graph for future agentic revision planning
- [ ] Currently deterministic — only migrate if agentic behavior added

### Phase 8: Agentic/MCP Capabilities (Week 6+)
- [ ] MCP tool definitions wrapping existing tools
- [ ] LangGraph agent with `tools` + `tool_calling` LLM
- [ ] Guardrails: max iterations, max tool calls, timeouts, allowlist

---

## 8. Ask StudyAI Refactor Plan (Feature 1 — Detailed)

### 8.1 Current Flow (Classic)

```
User Question
    ↓
RetrievalService.search(profile, query, subject, top_k=4)
    ↓
LLM.generate_structured(Prompt(name="chat", version="v1", user="EVIDENCE_JSON:..."))
    ↓
Parse answer + cited_chunk_ids
    ↓
EvidenceVerifier._classify(answer, cited_contents)
    ↓
Persist ChatMessage with citations + verification status
```

### 8.2 Target LangGraph Flow

```
State: ChatState
  - user_request: str
  - profile_id: UUID
  - subject_id: UUID | None
  - session_id: UUID
  - retrieved_evidence: list[Evidence]
  - selected_evidence: list[Evidence]
  - answer: str
  - citations: list[Citation]
  - verification_status: str
  - verification_score: float
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
retrieve_node ──────────────────► (on error) ─► error_node ─► END
    │
    ▼
evidence_selection_node (optional: re-rank, filter)
    │
    ▼
answer_generation_node ────────► (on error) ─► error_node ─► END
    │
    ▼
citation_verification_node
    │
    ├── supported/partial ─► format_response_node ─► END
    │
    └── unsupported ─► retry_answer_node (max 1 retry) ─► format_response_node ─► END
```

### 8.3 Node Specifications

| Node | Input | Output | LangSmith Run Name | Retries |
|------|-------|--------|-------------------|---------|
| `retrieve_node` | `user_request`, `profile_id`, `subject_id` | `retrieved_evidence` | `studyai.chat.retrieve` | 0 |
| `evidence_selection_node` | `retrieved_evidence`, `user_request` | `selected_evidence` | `studyai.chat.select_evidence` | 0 |
| `answer_generation_node` | `selected_evidence`, `user_request` | `answer`, `citations` | `studyai.chat.generate` | 1 |
| `citation_verification_node` | `answer`, `citations` | `verification_status`, `verification_score` | `studyai.chat.verify` | 0 |
| `retry_answer_node` | `answer`, `verification_details` | `answer`, `citations` | `studyai.chat.retry` | 0 |
| `format_response_node` | `answer`, `citations`, `verification` | `final_output` | `studyai.chat.format` | 0 |

### 8.4 Integration Point

```python
# apps/chat/services.py
def _ask_classic(session: ChatSession, content: str) -> ChatMessage:
    from ai.langgraph.graphs.chat_graph import chat_graph
    from ai.langgraph.state.chat_state import ChatState
    
    initial_state = ChatState(
        user_request=content,
        profile_id=session.profile_id,
        subject_id=session.subject_id,
        session_id=session.pk,
    )
    
    # Invoke with LangSmith tracing
    final_state = chat_graph.invoke(initial_state, config={"run_name": "studyai.chat.classic"})
    
    # Persist using existing logic (or extracted helper)
    return _persist_chat_message(session, final_state)
```

### 8.5 Preserved Behaviors

- Profile/subject scoping (enforced in `RetrievalService.search` → `StudyAIRetriever`)
- Hybrid retrieval (dense + keyword + RRF)
- Revision awareness (chunks carry `revision_ids`)
- Citation verification (deterministic `EvidenceVerifier`)
- Prompt version tracking (`CHAT_PROMPT_VERSION`)
- API contract (same `ChatMessage` response shape)
- Budget enforcement (`assert_within_budget`)

---

## 9. Dependencies to Add/Change

### 9.1 Add to `backend/requirements.txt`

```txt
# LangGraph orchestration
langgraph>=0.2.0

# LangChain core + Ollama integration
langchain-core>=0.3.0
langchain-community>=0.3.0
langchain-ollama>=0.2.0

# LangSmith tracing
langsmith>=0.1.0

# Optional: Postgres checkpointer for LangGraph persistence
# langgraph-checkpoint-postgres>=1.0.0  (when needed for human-in-the-loop)
```

### 9.2 Version Compatibility Notes

- `langgraph` 0.2+ requires `langchain-core` 0.3+
- `langchain-ollama` is the official Ollama integration (replaces community `ChatOllama`)
- Python 3.11+ (already used by Django 6.1)
- `pgvector` 0.3+ compatible

### 9.3 No Changes To

- `django`, `djangorestframework`, `celery`, `redis`
- `pgvector`, `sentence-transformers`, `tesserocr`
- `jsonschema`, `pydantic` (already used)

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **LangGraph introduces breaking changes** | Medium | High | Pin versions; test each feature in isolation; keep fallback to classic implementation |
| **LangSmith tracing adds latency** | Low | Medium | Batch spans; async export; disable in load tests; `LANGSMITH_TRACING=false` for perf tests |
| **Provider adapter breaks existing behavior** | Medium | High | Run full test suite against both old and new provider; compare outputs for same prompts |
| **Migration changes API behavior** | Low | High | Feature flags (`USE_LANGGRAPH_CHAT`); run both paths in shadow mode; compare responses |
| **Agent tool loop runs away** | Medium | High | Hard limits: `max_iterations`, `max_tool_calls`, `request_timeout`; circuit breakers |
| **Sensitive data leaked to LangSmith** | Low | Critical | Sanitization in tracing layer; never log `Prompt.user` raw; metadata-only for evidence |
| **Evaluation datasets insufficient** | High | Medium | Prioritize dataset creation alongside migration; use synthetic + curated cases |
| **Team unfamiliar with LangGraph** | High | Medium | Internal docs; pair programming; spike on chat graph first |
| **Circular imports (ai/ ↔ apps/)** | Medium | Medium | `ai/` imports from `apps/` only; `apps/` imports from `ai/` only via explicit entry points |

---

## 11. Approval Checklist

Before Phase 1 implementation begins:

- [ ] Architecture audit reviewed and approved
- [ ] Migration plan approved (feature order, timeline)
- [ ] LangSmith project created, API key provisioned in secrets manager
- [ ] Dependencies approved for addition
- [ ] Directory structure `backend/ai/` approved
- [ ] Provider adapter strategy approved
- [ ] Tracing policy (what to trace, what not to trace) approved
- [ ] Rollback plan for each feature documented

---

## Appendix: Key Files Reference

| File | Purpose |
|------|---------|
| `backend/providers/base.py` | Provider Protocols (`LLMProvider`, `EmbeddingProvider`, `OCRProvider`) |
| `backend/providers/registry.py` | Provider factory (`get_llm_provider`, `get_embedding_provider`, `get_ocr_provider`) |
| `backend/providers/llm/chain.py` | `LLMChainProvider` fallback + sanitization + telemetry |
| `backend/providers/llm/local.py` | `OllamaLLMProvider`, `OllamaChatProvider` |
| `backend/apps/chat/services.py` | `ChatService.ask()` — classic + agent modes |
| `backend/apps/agents/services/orchestrator.py` | `AgentOrchestrator` — custom agent loop |
| `backend/apps/agents/tools/learning.py` | Agent tools (mastery, revision, questions, test generation) |
| `backend/apps/ai_classroom/services.py` | `run_enrichment_job()` — 6-stage pipeline |
| `backend/apps/ai_classroom/prompts.py` | `PromptTemplate`, `active_prompt()`, `validate_stage_output()` |
| `backend/apps/retrieval/services.py` | `index_document()`, `build_chunks()`, hybrid retrieval |
| `backend/apps/retrieval/retrieval.py` | `RetrievalService.search()` — RRF hybrid search |
| `backend/apps/questions/services.py` | `QuestionGenerationService.generate_for_document()` |
| `backend/apps/revision/services.py` | `RevisionPlanningService.build_plan()` — deterministic |
| `backend/apps/evaluation/runner.py` | Evaluation harness (retrieval, citation, agent metrics) |
| `backend/apps/jobs/services.py` | Job dispatch, execution, retry, reaper |
| `backend/config/settings/base.py` | All AI-related settings (provider chains, budgets, agent config) |

---

**Next Step:** Await approval to begin **Phase 1: Foundation** implementation.