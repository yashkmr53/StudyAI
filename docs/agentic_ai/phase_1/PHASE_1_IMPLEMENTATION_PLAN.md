# Phase 1 — Agentic AI Layer: Implementation Plan

**Date:** 2026-08-24  
**Status:** IN PROGRESS  
**Target:** Transform "Ask StudyAI" from fixed RAG chatbot to extensible Agentic AI interface

---

## Implementation Order

### Step 1: Create `agents` Django App Structure
- [ ] `backend/apps/agents/__init__.py`
- [ ] `backend/apps/agents/apps.py`
- [ ] `backend/apps/agents/models.py` — AgentExecutionLog, AgentPromptVersion
- [ ] `backend/apps/agents/migrations/0001_initial.py` (after makemigrations)

### Step 2: Tool Abstraction Layer
- [ ] `backend/apps/agents/tools/base.py` — Tool protocol, base classes, registry
- [ ] `backend/apps/agents/tools/retrieval.py` — SearchNotesTool, SearchReferenceBooksTool
- [ ] `backend/apps/agents/tools/learning.py` — GetMasteryTool (initial)
- [ ] `backend/apps/agents/tools/evidence.py` — VerifyEvidenceTool
- [ ] `backend/apps/agents/tools/document.py` — GetDocumentTool, GetSubjectContextTool

### Step 3: Agent Orchestrator
- [ ] `backend/apps/agents/services/orchestrator.py` — Reasoning loop, tool selection, limits
- [ ] `backend/apps/agents/services/agent.py` — StudyAIAgent high-level interface
- [ ] `backend/apps/agents/services/telemetry.py` — Execution logging, metrics
- [ ] `backend/apps/agents/prompts/agent_prompts.py` — System prompts

### Step 4: API Integration
- [ ] `backend/apps/agents/serializers.py` — Request/response schemas
- [ ] `backend/apps/agents/views.py` — Agent chat endpoint
- [ ] `backend/apps/agents/urls.py` — Route registration
- [ ] `backend/apps/chat/services.py` — Add `ask_agent()` method
- [ ] `backend/apps/chat/views.py` — Header-based agent mode switch

### Step 5: Configuration & Settings
- [ ] `backend/config/settings/` — Agent constants (max_iterations, timeouts, etc.)
- [ ] `.env.example` — Agent-related env vars

### Step 6: Frontend Integration
- [ ] `frontend/src/services/api/agent.ts` — API client
- [ ] `frontend/src/types/agent.ts` — TypeScript interfaces
- [ ] `frontend/src/components/chat/ToolStatusIndicator.tsx` — Activity display
- [ ] `frontend/src/components/chat/AgentMessageBubble.tsx` — Enhanced message
- [ ] `frontend/src/components/chat/ChatPage.tsx` — Integrate agent mode
- [ ] `frontend/src/hooks/useAgentChat.ts` — Chat hook

### Step 7: Tests
- [ ] `backend/apps/agents/tests/test_tools.py` — Tool unit tests
- [ ] `backend/apps/agents/tests/test_agent.py` — Agent orchestration tests
- [ ] `backend/apps/agents/tests/test_integration.py` — End-to-end tests
- [ ] Frontend component tests (if test infrastructure exists)

### Step 8: Verification
- [ ] Run backend tests: `docker compose run --rm api python -m pytest backend/apps/agents/tests/ -v`
- [ ] Run full test suite: `docker compose run --rm api python -m pytest backend/tests/ -v`
- [ ] Lint/typecheck: `docker compose run --rm api python -m ruff check backend/apps/agents/`
- [ ] Manual test: agentic chat flow in browser

---

## Detailed File Specifications

### 1. `backend/apps/agents/models.py`
```python
# AgentExecutionLog - audit trail for every agent execution
# AgentPromptVersion - versioned system prompts for agent
# Indexes on request_id, profile, created_at
```

### 2. `backend/apps/agents/tools/base.py`
```python
# ToolInput/ToolOutput - Pydantic base models
# ToolMetadata - dataclass with name, description, schemas, auth, timeout, category
# Tool protocol - execute(input, user, request_id) -> output
# ToolRegistry - singleton registry: register(), get(), list()
```

### 3. `backend/apps/agents/tools/retrieval.py`
```python
# SearchNotesTool - wraps RetrievalService.search(include_reference=False)
# SearchReferenceBooksTool - wraps RetrievalService.search(include_reference=True) + filter
# Input: query, subject_id?, top_k?
# Output: list[EvidenceResult] with chunk_id, snippet, scores, source_type
```

### 4. `backend/apps/agents/tools/learning.py`
```python
# GetMasteryTool - wraps RevisionPlanningService.overview(profile)
# Input: subject_id?
# Output: tags[], assessed_count, not_assessed_count
```

### 5. `backend/apps/agents/tools/evidence.py`
```python
# VerifyEvidenceTool - wraps EvidenceVerifier.verify(content, source_refs)
# Input: content, source_refs[]
# Output: status, score, verifier_version
```

### 6. `backend/apps/agents/services/orchestrator.py`
```python
# AgentOrchestrator class
# - max_iterations: int = 5
# - max_tool_calls: int = 10
# - request_timeout_seconds: int = 60
# - per_tool_timeout_seconds: int = 30
# - run(user_request, user, session, request_id) -> AgentResult
# - _select_tool() - LLM-based tool selection
# - _execute_tool() - schema validation, auth, timeout, telemetry
# - _should_continue() - decide if more tools needed
```

### 7. `backend/apps/agents/services/agent.py`
```python
# StudyAIAgent class
# - orchestrator: AgentOrchestrator
# - tool_registry: ToolRegistry
# - process_request(user_request, user, session) -> AgentResponse
# AgentResponse: answer, citations, tool_calls[], trace_id
```

### 8. `backend/apps/agents/prompts/agent_prompts.py`
```python
# AGENT_SYSTEM_PROMPT = """
# You are StudyAI Agent. You have access to tools...
# Tool descriptions injected dynamically from registry.
# """
# TOOL_DESCRIPTION_TEMPLATE = "- {name}: {description}\n  Input: {input_schema}\n  Output: {output_schema}"
```

### 9. `backend/apps/agents/views.py`
```python
# AgentChatViewSet
# POST /agents/chat/ {session_id, content} -> AgentResponse
# GET /agents/tools/ -> list[ToolMetadata]
# GET /agents/executions/{request_id}/ -> AgentExecutionLog
```

### 10. `backend/apps/chat/services.py` addition
```python
# ChatService.ask_agent(session, content) -> ChatMessage
# Uses StudyAIAgent internally, persists messages with tool_calls JSON
```

### 11. `frontend/src/services/api/agent.ts`
```typescript
// agentApi.sendMessage(sessionId, content) -> AgentResponse
// agentApi.listTools() -> ToolMetadata[]
// agentApi.getExecutionTrace(requestId) -> AgentExecutionLog
```

### 12. `frontend/src/types/agent.ts`
```typescript
interface ToolCall {
  tool: string;
  status: "pending" | "running" | "success" | "error";
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  latencyMs?: number;
}

interface AgentResponse {
  user: ChatMessageItem;
  assistant: ChatMessageItem & { toolCalls?: ToolCall[]; traceId?: string };
}

interface ToolMetadata {
  name: string;
  description: string;
  category: "retrieval" | "learning" | "evidence" | "document";
  inputSchema: JSONSchema;
  outputSchema: JSONSchema;
}
```

---

## Configuration Constants (backend/config/settings/base.py additions)

```python
# Agent Orchestration Limits
AGENT_MAX_ITERATIONS = 5
AGENT_MAX_TOOL_CALLS = 10
AGENT_REQUEST_TIMEOUT_SECONDS = 60
AGENT_PER_TOOL_TIMEOUT_SECONDS = 30

# Agent Prompt Version
AGENT_PROMPT_VERSION = "agent_orchestrator:v1"

# Tool Timeouts (per-tool override)
AGENT_TOOL_TIMEOUTS = {
    "search_notes": 15,
    "search_reference_books": 15,
    "get_mastery": 5,
    "verify_evidence": 10,
    "get_document": 5,
    "get_subject_context": 5,
}

# Enable agentic mode (feature flag)
AGENT_ENABLED = True
```

---

## Environment Variables (.env.example additions)

```bash
# --- Agentic AI (Phase 1) ---
AGENT_MAX_ITERATIONS=5
AGENT_MAX_TOOL_CALLS=10
AGENT_REQUEST_TIMEOUT_SECONDS=60
AGENT_PER_TOOL_TIMEOUT_SECONDS=30
AGENT_ENABLED=true
```

---

## Database Migration

```bash
# After creating models.py
docker compose run --rm api python manage.py makemigrations agents
docker compose run --rm api python manage.py migrate
```

---

## Key Integration Points

### Chat Service Integration
```python
# In ChatService.ask() - add agent mode detection
@staticmethod
@transaction.atomic
def ask(session: ChatSession, content: str, *, use_agent: bool = False) -> ChatMessage:
    if use_agent and settings.AGENT_ENABLED:
        return ChatService.ask_agent(session, content)
    # ... existing fixed RAG flow
```

### Tool Authorization Pattern
```python
# Every tool.execute() follows this pattern:
def execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
    # 1. Validate input schema (Pydantic)
    # 2. Get profile from user
    profile = Profile.objects.get(user=user)
    # 3. ProfileAuthorizationService.ensure_profile_access(user, profile)
    # 4. Call domain service with profile-scoped queries
    # 5. Return validated output
```

---

## Test Cases to Implement

### Tool Unit Tests
| Test | Description |
|------|-------------|
| `test_search_notes_valid_input` | Valid query returns EvidenceResult[] |
| `test_search_notes_empty_query` | Empty query returns [] |
| `test_search_notes_auth_enforcement` | Wrong profile raises Forbidden |
| `test_search_reference_books_filters_correctly` | Only source_type="reference" returned |
| `test_get_mastery_returns_structured_data` | Tags with mastery scores |
| `test_verify_evidence_supported` | High lexical overlap -> supported |
| `test_verify_evidence_unsupported` | No overlap -> unsupported |

### Agent Orchestration Tests
| Test | Description |
|------|-------------|
| `test_simple_question_single_tool` | "What is X?" -> search_notes -> answer |
| `test_multi_step_reasoning` | Weak topic test -> get_mastery -> search_notes -> generate_questions |
| `test_max_iterations_limit` | Agent stops after 5 iterations |
| `test_max_tool_calls_limit` | Agent stops after 10 tool calls |
| `test_tool_failure_retry` | Failed tool retries once then continues |
| `test_cross_profile_blocked` | Tool rejects other user's data |
| `test_prompt_injection_handled` | Retrieved content with injection -> LLM chain directive handles |

### Integration Tests
| Test | Description |
|------|-------------|
| `test_agent_chat_endpoint` | POST /agents/chat/ returns grounded answer |
| `test_agent_mode_header` | X-Agent-Mode: true triggers agent |
| `test_classic_chat_unchanged` | Existing /chat/sessions/{id}/messages works |
| `test_frontend_tool_status` | Tool activity indicators appear |

---

## Frontend Integration Details

### ChatPage.tsx Modifications
1. Add agent mode toggle (button in header)
2. Replace `chatApi.sendMessage` with `agentApi.sendMessage` when agent mode active
3. Render `ToolCall` status in message bubbles (pending/running/success/error)
4. Show activity labels: "Searching your notes...", "Analyzing mastery...", etc.
5. Display `traceId` for debugging (collapsible)

### Tool Status Mapping
```typescript
const TOOL_STATUS_LABELS: Record<string, string> = {
  search_notes: "Searching your notes...",
  search_reference_books: "Checking reference material...",
  get_mastery: "Analyzing mastery...",
  verify_evidence: "Verifying sources...",
  get_document: "Loading document...",
  get_subject_context: "Loading subject context...",
};
```

---

## Rollback Plan

If issues arise:
1. Disable agent via `AGENT_ENABLED=false` env var
2. Existing `/chat/sessions/{id}/messages` endpoint unchanged
3. Frontend falls back to classic chat automatically
4. No database migration rollback needed (additive only)

---

## Success Criteria

- [ ] Agent answers simple questions using `search_notes` tool
- [ ] Agent identifies weak topics via `get_mastery` and generates targeted questions
- [ ] Tool activity visible in frontend during execution
- [ ] Execution trace logged with full tool call sequence
- [ ] All security guardrails enforced (auth, schema, limits)
- [ ] Existing chat functionality 100% preserved
- [ ] All tests pass in CI