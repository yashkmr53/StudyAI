# Phase 1 — StudyAI Agentic AI Layer: Architecture Audit & Implementation Plan

**Date:** 2026-08-24  
**Status:** IN PROGRESS  
**Source:** Senior AI/LLM Systems Engineer task to add Agentic AI layer on top of existing StudyAI architecture

---

## 1. Current Architecture Assessment

### 1.1 Backend Stack (Django + DRF)
- **Framework:** Django 4.x with Django REST Framework
- **Database:** PostgreSQL with pgvector extension for embeddings
- **Async/Jobs:** Celery + Redis for background job processing
- **Auth:** Session-based with profile-scoped authorization (RLS at DB layer)
- **Observability:** In-process metrics + Prometheus counters, request timing middleware

### 1.2 Existing AI Infrastructure (Phase 11 Complete)
| Capability | Implementation | Provider Abstraction |
|------------|---------------|---------------------|
| **OCR** | Tesseract / PaddleOCR / Mock | `OCRChainProvider` with fallback |
| **LLM** | Ollama (local) / Mock | `LLMChainProvider` with fallback, prompt-injection defense, PII sanitization |
| **Embeddings** | sentence-transformers / Hashing / Mock | `EmbeddingProvider` protocol with versioning |
| **Storage** | MinIO (S3-compatible) / Local | `ObjectStorageProvider` protocol |
| **Email** | Mailpit / SMTP / Console | `EmailProvider` protocol |

### 1.3 Existing Domain Services (Source of Truth - MUST NOT REWRITE)

| Service | App | Key Responsibility |
|---------|-----|-------------------|
| **Hybrid Retrieval** | `retrieval` | Dense (pgvector) + Keyword (tsvector) → RRF, profile/subject scoping |
| **Incremental Indexing** | `retrieval.services` | Content-hash-based diff, stale chunk marking, tsvector population |
| **Evidence Verification** | `ai_classroom.services.EvidenceVerifier` | Lexical support scoring, threshold-based classification |
| **Enrichment Pipeline** | `ai_classroom.services.EnrichmentService` | A→B→C→D→E→F stages with schema validation |
| **Question Generation** | `questions.services.QuestionGenerationService` | Deterministic MCQs bound to source chunk/revision |
| **Mastery Scoring** | `tests.services.MasteryScoringService` | EMA update on attempts, not_assessed for untried tags |
| **Test Generation** | `tests.services.TestGenerationService` | Priority ordering: weakness > recency > difficulty |
| **Revision Planning** | `revision.services.RevisionPlanningService` | Deterministic priority: weakness/urgency/failures/insufficient |
| **Reference Books** | `references` | Platform-curated, READY-gated retrieval inclusion |
| **Chat ("Ask StudyAI")** | `chat` | Scoped retrieval → LLM → citation verification → persist |
| **Provider Telemetry** | `providers.llm.chain` | ProviderCallLog for every attempt with latency/tokens |

### 1.4 Current "Ask StudyAI" Flow (Fixed RAG Chatbot)
```
User Request → ChatSession → RetrievalService.search() → LLM.generate_structured()
    → EvidenceVerifier.verify() → ChatMessage (with citations) → Response
```
**Limitations:** Single retrieval step, no tool selection, no multi-step reasoning, no access to mastery/test/revision services.

### 1.5 Frontend (React 19 + Vite)
- **Chat UI:** `frontend/src/components/chat/ChatPage.tsx` — subject-scoped sessions, message list, citations display
- **API Client:** `frontend/src/services/api/chat.ts` — defensive wire format parsing
- **State:** Zustand store (`workspaceStore`) for subjects/profile context

---

## 2. Components/Services Reusable as Agent Tools

The following existing service methods map directly to agent tools (read-only orchestration, no business logic duplication):

### Retrieval Tools
| Tool | Service Method | Input | Output |
|------|---------------|-------|--------|
| `search_notes` | `RetrievalService.search(user, query, subject, top_k, include_reference=False)` | query, subject?, top_k? | `list[Evidence]` (chunk_id, content_snippet, source_type, page_range, scores) |
| `search_reference_books` | `RetrievalService.search(user, query, subject, top_k, include_reference=True)` + filter `source_type=="reference"` | query, subject?, top_k? | `list[Evidence]` (reference chunks only) |

### Learning Tools
| Tool | Service Method | Input | Output |
|------|---------------|-------|--------|
| `get_mastery` | `RevisionPlanningService.overview(profile)` | profile_id | `{tags: [{tag_id, stable_key, display_name, status, mastery, attempt_count, last_assessed_at}], assessed_count, not_assessed_count}` |
| `get_revision_plan` | `RevisionPlanningService.build_plan(profile, subject, target_date)` | profile_id, subject?, target_date | `{target_date, days_left, priorities[], schedule[]}` |
| `get_previous_questions` | `Question.objects.filter(document__profile__user=..., stale=False)` + tag linkage | profile_id, subject?, tag?, limit? | `list[Question]` (prompt, options, answer_index, difficulty, tags) |
| `generate_questions` | `QuestionGenerationService.generate_for_document(document, max_questions)` | document_id, count?, difficulty? | `list[Question]` (persisted, revision-bound) |
| `create_test` | `TestGenerationService.build_test(profile, subject, num_questions, type)` | profile_id, subject?, num_questions?, type? | `TestInstance` with `TestQuestion[]` |

### Evidence Tools
| Tool | Service Method | Input | Output |
|------|---------------|-------|--------|
| `verify_evidence` | `EvidenceVerifier.verify(block_content, source_refs)` | block_content, source_refs[] | `{status: supported|partially_supported|unsupported|not_verified, score: float}` |
| `verify_citations` | `EvidenceVerifier.verify()` per citation block | list of (content, refs) | `list[verification_result]` |

### Document/Context Tools
| Tool | Service Method | Input | Output |
|------|---------------|-------|--------|
| `get_document` | `Document.objects.get(pk, profile__user=...)` | document_id | `Document` (title, pages, revisions, source_type) |
| `get_document_revision` | `DocumentPageRevision.objects.get(pk)` | revision_id | `DocumentPageRevision` (lines, content_hash) |
| `get_subject_context` | `Subject.objects.get(pk, profile__user=...)` + linked documents | subject_id | `{subject, documents[], tags[]}` |

---

## 3. Proposed Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        StudyAI Agent                            │
│  (Orchestrator: intent → plan → tool calls → observe → respond) │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tool Registry                              │
│  (name → Tool instance; schema validation; auth; timeout)      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Retrieval Tools    │ │  Learning Tools │ │  Evidence Tools │
│  - search_notes     │ │  - get_mastery  │ │  - verify_      │
│  - search_ref_books │ │  - get_revision │ │    evidence     │
└─────────────────────┘ │  - gen_questions│ │  - verify_      │
                        │  - create_test  │ │    citations    │
                        └─────────────────┘ └─────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Existing Domain Services                       │
│  (RetrievalService, EvidenceVerifier, MasteryScoringService,   │
│   QuestionGenerationService, TestGenerationService,            │
│   RevisionPlanningService, EnrichmentService)                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              PostgreSQL / pgvector / Redis / Celery             │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities (ONLY)
- Understanding user intent (classify request type)
- Deciding whether tools are required
- Selecting appropriate tools from registry
- Constructing valid tool arguments (schema-validated)
- Executing multi-step workflows (loop: act → observe → decide)
- Deciding whether additional tool calls are needed
- Producing final grounded response with citations

### Agent MUST NOT
- Contain business logic that exists in domain services
- Access database directly (bypass services)
- Calculate mastery scores, RRF, verification scores
- Construct SQL or bypass RLS
- Choose arbitrary profile IDs

---

## 4. Proposed Tool Registry & Schemas

### Base Tool Interface (`backend/apps/agents/tools/base.py`)
```python
from dataclasses import dataclass
from typing import Protocol, Any
from pydantic import BaseModel

class ToolInput(BaseModel):
    """Base input schema — all tools must define concrete schema."""
    pass

class ToolOutput(BaseModel):
    """Base output schema — all tools must define concrete schema."""
    pass

@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: type[ToolInput]
    output_schema: type[ToolOutput]
    requires_auth: bool = True
    timeout_seconds: int = 30
    max_retries: int = 1
    category: str = "general"  # retrieval | learning | evidence | document

class Tool(Protocol):
    metadata: ToolMetadata
    
    def execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
        ...
```

### Concrete Tool Schemas (Pydantic models for validation)

#### Retrieval Tools
```python
# search_notes
class SearchNotesInput(ToolInput):
    query: str
    subject_id: str | None = None
    top_k: int = 8

class SearchNotesOutput(ToolOutput):
    results: list[EvidenceResult]  # chunk_id, document_id, source_type, page_start, page_end, snippet, scores
    query: str

# search_reference_books  
class SearchReferenceBooksInput(ToolInput):
    query: str
    subject_id: str | None = None
    top_k: int = 6

class SearchReferenceBooksOutput(ToolOutput):
    results: list[EvidenceResult]
    query: str
```

#### Learning Tools
```python
# get_mastery
class GetMasteryInput(ToolInput):
    subject_id: str | None = None

class GetMasteryOutput(ToolOutput):
    tags: list[MasteryTag]  # tag_id, stable_key, display_name, status, mastery, attempt_count, last_assessed_at
    assessed_count: int
    not_assessed_count: int

# get_revision_plan
class GetRevisionPlanInput(ToolInput):
    subject_id: str | None = None
    target_date: str  # ISO date

class GetRevisionPlanOutput(ToolOutput):
    target_date: str
    days_left: int
    priorities: list[PriorityTag]  # tag_id, display_name, status, priority
    schedule: list[DailySchedule]  # date, focus[]

# generate_questions
class GenerateQuestionsInput(ToolInput):
    document_id: str
    count: int = 10
    difficulty: str | None = None  # easy|medium|hard
    focus_weak_topics: bool = False

class GenerateQuestionsOutput(ToolOutput):
    questions: list[GeneratedQuestion]  # id, prompt, options, answer_index, difficulty, source_chunk_id
    test_id: str | None = None

# create_test
class CreateTestInput(ToolInput):
    subject_id: str | None = None
    num_questions: int = 10
    test_type: str = "practice"  # practice|mock

class CreateTestOutput(ToolOutput):
    test_id: str
    questions: list[TestQuestionRef]  # question_id, order
```

#### Evidence Tools
```python
# verify_evidence
class VerifyEvidenceInput(ToolInput):
    content: str
    source_refs: list[SourceRef]  # chunk_id, document_id, page_number, revision_id

class VerifyEvidenceOutput(ToolOutput):
    status: str  # supported|partially_supported|unsupported|not_verified
    score: float | None
    verifier_version: str
```

---

## 5. MCP Integration Approach

### Architecture
```
Domain Services (source of truth)
         ↑
Internal Tool Layer (this phase - strongly typed, auth-enforced)
         ↑
MCP Adapter (future phase - exposes selected tools via MCP protocol)
         ↑
StudyAI Agent / External MCP Clients
```

### Design Principles
1. **No coupling to MCP in domain services** — tools are plain Python classes
2. **MCP Adapter is a thin translation layer** — maps MCP tool calls → internal tool execution
3. **Auth enforced at Internal Tool Layer** — MCP adapter passes authenticated user context
4. **Schema compatibility** — Internal tool schemas (Pydantic) map to MCP JSON Schema
5. **Observability preserved** — MCP calls logged with same telemetry as internal calls

### Phase 1 Scope
- Build Internal Tool Layer only
- Design MCP Adapter interface (defer implementation to Phase 3)
- Tool registry designed to support MCP exposure (metadata includes MCP-compatible descriptions)

---

## 6. Security / Guardrail Design

### Authorization Flow (Preserves Existing)
```
Agent Request
    ↓
Tool.execute(input, user=request.user, request_id=...)
    ↓
ProfileAuthorizationService.ensure_profile_access(user, profile)
    ↓
Domain Service (scoped queries only)
    ↓
Database (RLS enforced)
```

### Guardrails Implemented in Tool Layer
| Guardrail | Implementation |
|-----------|----------------|
| **Schema Validation** | Pydantic models on all tool inputs/outputs |
| **Profile Isolation** | `user` passed to every tool; service layer enforces ownership |
| **RLS** | Database-level row-level security (existing) |
| **Input Limits** | `MAX_PROVIDER_INPUT_CHARS` applied in LLM chain (existing) |
| **Prompt Injection Defense** | Directive prepended in `LLMChainProvider` (existing) |
| **AI Budgets** | `assert_within_budget(profile_id)` checked before LLM calls (existing) |
| **Tool Allowlist** | Agent only sees registered tools; no dynamic invocation |
| **Execution Limits** | Configurable: max_tool_calls, max_iterations, request_timeout, per_tool_timeout |

### Data Classification
- **User notes & reference books** = UNTRUSTED (may contain prompt injection)
- **Tool arguments** = VALIDATED (Pydantic schema)
- **LLM outputs** = SCHEMA-VALIDATED (jsonschema per prompt version)

---

## 7. Observability Design

### Extended Telemetry (added to existing `ProviderCallLog` pattern)

#### Agent Execution Log (new model: `AgentExecutionLog`)
| Field | Description |
|-------|-------------|
| `id` | UUID |
| `request_id` | Correlation ID (matches chat session/message) |
| `user_id` | Profile user |
| `intent_category` | question_answering, test_generation, revision_planning, etc. |
| `model_provider` | From provider registry |
| `model_name` | e.g., "llama3.1:8b" |
| `prompt_version` | Agent system prompt version |
| `tool_call_sequence` | JSON: `[{tool, args_hash, latency_ms, success, error}]` |
| `iterations` | Number of agent reasoning steps |
| `retrieved_evidence_ids` | List of chunk_ids used |
| `total_tokens` | Input + output tokens |
| `total_latency_ms` | End-to-end |
| `outcome` | success | partial | failed | limit_reached |
| `citation_verification_status` | Overall verification result |
| `guardrail_violations` | Count of schema/auth/limit violations |

#### Metrics (Prometheus)
- `agent_executions_total{outcome}` — Counter
- `agent_tool_calls_total{tool,success}` — Counter  
- `agent_iterations_histogram` — Histogram
- `agent_tool_latency_seconds{tool}` — Histogram
- `agent_token_usage_total{model}` — Counter

#### Structured Logging
Each agent iteration logs:
```
agent.iteration request_id=... iteration=1 tool=search_notes args_hash=abc123 
    latency_ms=245 success=true evidence_count=4
agent.iteration request_id=... iteration=2 tool=get_mastery args_hash=def456
    latency_ms=12 success=true weak_tags=3
agent.complete request_id=... iterations=3 tools=2 tokens=1847 latency_ms=892 
    outcome=success verification=supported
```

---

## 8. Database Changes

### New Models (backend/apps/agents/models.py)
```python
class AgentExecutionLog(models.Model):
    """Audit trail for every agent execution."""
    id = UUIDField(pk=True)
    request_id = CharField(64)  # correlates with chat message / API request
    profile = FK(Profile)
    intent_category = CharField(32)
    model_provider = CharField(64)
    model_name = CharField(128)
    prompt_version = CharField(64)
    tool_call_sequence = JSONField(default=list)
    iterations = PositiveIntegerField(default=0)
    retrieved_evidence_ids = JSONField(default=list)
    total_tokens = PositiveIntegerField(default=0)
    total_latency_ms = PositiveIntegerField(default=0)
    outcome = CharField(choices=Outcome.choices)
    citation_verification_status = CharField(choices=VerificationStatus.choices, null=True)
    guardrail_violations = PositiveIntegerField(default=0)
    created_at = DateTimeField(auto_now_add=True)

class AgentPromptVersion(models.Model):
    """Versioned agent system prompts (mirrors PromptVersion pattern)."""
    name = CharField(64)  # "agent_orchestrator"
    version = CharField(16)
    system_template = TextField()
    tool_descriptions = JSONField(default=dict)  # injected at runtime
    is_active = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
```

### Migration Strategy
- New app `agents` with models above
- No changes to existing tables
- Indexes on `request_id`, `profile`, `created_at` for querying

---

## 9. API Changes

### New Endpoints (under `/api/agents/`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/agents/chat/` | Agentic chat (replaces/enhances `/chat/sessions/{id}/messages`) |
| GET | `/agents/tools/` | List available tools (for frontend tool status display) |
| GET | `/agents/executions/{request_id}/` | Get execution trace (debugging) |

### Backward Compatibility
- Existing `/chat/sessions/{id}/messages` continues to work (fixed RAG)
- New agentic endpoint is opt-in via header `X-Agent-Mode: true` or separate URL
- Response format extends existing `ChatMessage` with `tool_calls` and `agent_trace`

---

## 10. Frontend Changes

### ChatPage Enhancements
1. **Tool Activity Indicators** — Show "Searching your notes...", "Checking reference material...", "Analyzing mastery..."
2. **Citation Display** — Already exists, enhance with verification status badges
3. **Structured Outputs** — Render generated questions, test links, revision plan cards
4. **Error Recovery** — Show tool failures with retry option
5. **Agent Mode Toggle** — Switch between classic RAG and agentic mode

### New Types (`frontend/src/types/agent.ts`)
```typescript
interface ToolCall {
  tool: string;
  status: "pending" | "running" | "success" | "error";
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  latencyMs?: number;
}

interface AgentMessage extends ChatMessageItem {
  toolCalls?: ToolCall[];
  agentTraceId?: string;
}
```

---

## 11. File-by-File Implementation Plan

### Phase 1: Core Agent Infrastructure

#### Backend — New App: `agents`
```
backend/apps/agents/
├── __init__.py
├── apps.py
├── models.py                 # AgentExecutionLog, AgentPromptVersion
├── tools/
│   ├── __init__.py
│   ├── base.py               # Tool, ToolInput, ToolOutput, ToolMetadata, ToolRegistry
│   ├── retrieval.py          # SearchNotesTool, SearchReferenceBooksTool
│   ├── learning.py           # GetMasteryTool, GetRevisionPlanTool, GetPreviousQuestionsTool
│   ├── evidence.py           # VerifyEvidenceTool, VerifyCitationsTool
│   └── document.py           # GetDocumentTool, GetSubjectContextTool
├── services/
│   ├── __init__.py
│   ├── agent.py              # StudyAIAgent (orchestrator)
│   ├── orchestrator.py       # Reasoning loop, tool selection, iteration limits
│   └── telemetry.py          # AgentExecutionLog recording, metrics
├── prompts/
│   ├── __init__.py
│   └── agent_prompts.py      # System prompts for orchestrator
├── views.py                  # Agent chat endpoint
├── serializers.py            # Request/response schemas
├── urls.py
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── __init__.py
    ├── test_tools.py
    ├── test_agent.py
    └── test_integration.py
```

#### Backend — Integration Points
- `backend/apps/chat/services.py` — Add `ChatService.ask_agent()` variant
- `backend/apps/chat/views.py` — Add agentic endpoint or header-based switching
- `backend/config/settings/` — Add agent configuration constants

#### Frontend
```
frontend/src/
├── services/api/
│   └── agent.ts              # Agent API client
├── components/chat/
│   ├── ChatPage.tsx          # Enhanced with tool status display
│   ├── ToolStatusIndicator.tsx
│   └── AgentMessageBubble.tsx
├── types/
│   └── agent.ts              # TypeScript interfaces
└── hooks/
    └── useAgentChat.ts       # Hook for agentic chat flow
```

### Phase 2: Extended Tools (Future)
- `generate_questions`, `create_test`, `get_previous_questions`, `get_revision_plan`
- Mastery-aware test generation workflow
- Citation verification integration

### Phase 3: MCP Adapter (Future)
- `backend/apps/agents/mcp/adapter.py`
- `backend/apps/agents/mcp/server.py`

---

## 12. Testing Strategy

### Unit Tests (per tool)
- `test_tools.py` — Each tool: valid input → expected output shape, auth enforcement, error handling
- Mock domain services to isolate tool logic

### Integration Tests
- `test_agent.py` — Full agent loop with mocked LLM provider
- Scenarios:
  1. Simple factual question → search_notes → answer
  2. Weak-topic test generation → get_mastery → search_notes → generate_questions → create_test
  3. Revision plan request → get_revision_plan → response
  4. Cross-profile access attempt → Forbidden
  5. Prompt injection in retrieved content → handled by LLM chain directive
  6. Tool failure → retry / fallback
  7. Max iterations reached → graceful degradation

### Evaluation Extensions (Phase 10 framework)
- Add agent-specific metrics to `evaluation/runner.py`:
  - Tool selection accuracy
  - Task completion rate
  - Unnecessary tool call rate
  - Average tool calls per task
  - Groundedness / hallucination rate

---

## 13. Risks & Trade-offs

| Risk | Mitigation |
|------|------------|
| **Agent loops infinitely** | Hard limits: max_iterations (default 5), max_tool_calls (default 10), request_timeout (60s) |
| **LLM selects wrong tool** | Structured tool descriptions in prompt; evaluation suite measures selection accuracy |
| **Schema drift between tool & service** | Pydantic schemas generated from service method signatures; CI check |
| **Performance regression** | Tool-level timeouts; async execution where possible; observability alerts |
| **Security bypass** | All tools enforce ProfileAuthorizationService; integration tests for cross-profile attempts |
| **Breaking existing chat** | Parallel implementation; feature flag / header toggle; backward-compatible API |

---

## 14. Verification Gates (Phase 1)

1. ✅ `docker compose up -d` — All services healthy
2. ✅ `docker compose run --rm api python -m pytest backend/apps/agents/tests/ -v` — All agent tests pass
3. ✅ Agentic chat endpoint returns grounded response with tool trace
4. ✅ Frontend shows tool activity states during agent execution
5. ✅ Cross-profile access blocked at tool layer
6. ✅ Execution limits enforced (max iterations, max tool calls)
7. ✅ Telemetry recorded in `AgentExecutionLog` and Prometheus metrics
8. ✅ Existing chat endpoint unchanged and functional
9. ✅ Schema validation rejects invalid tool arguments

---

## 15. Next Steps

1. **Create `agents` app** with models, base tool classes, registry
2. **Implement 3 core tools**: `search_notes`, `search_reference_books`, `get_mastery`
3. **Build `StudyAIAgent` orchestrator** with reasoning loop and limits
4. **Add telemetry** (`AgentExecutionLog`, Prometheus metrics)
5. **Integrate with chat** — new endpoint or header-based switch
6. **Frontend updates** — tool status indicators, enhanced message rendering
7. **Write tests** — unit + integration
8. **Document** — update this README with implementation details