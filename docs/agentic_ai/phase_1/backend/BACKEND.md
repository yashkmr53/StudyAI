# Phase 1 — Backend Implementation Reference

**Date:** 2026-08-24  
**Status:** COMPLETED

---

## File Structure

```
backend/apps/agents/
├── __init__.py                 # App config, tool registration
├── apps.py                     # AgentsConfig with ready() hook
├── models.py                   # AgentExecutionLog, AgentPromptVersion
├── migrations/
│   ├── __init__.py
│   └── 0001_initial.py         # Creates agent tables
├── tools/
│   ├── __init__.py             # Exports base classes + registry
│   ├── base.py                 # Tool protocol, BaseTool, ToolRegistry
│   ├── retrieval.py            # SearchNotesTool, SearchReferenceBooksTool
│   ├── learning.py             # GetMastery, GetRevisionPlan, GetPreviousQuestions, GenerateQuestions, CreateTest
│   ├── evidence.py             # VerifyEvidenceTool, VerifyCitationsTool
│   └── document.py             # GetDocumentTool, GetSubjectContextTool
├── services/
│   ├── __init__.py
│   ├── orchestrator.py         # AgentOrchestrator (reasoning loop)
│   ├── agent.py                # StudyAIAgent (high-level interface)
│   └── telemetry.py            # AgentExecutionLog + metrics
├── prompts/
│   ├── __init__.py
│   └── agent_prompts.py        # System prompt + tool descriptions
├── serializers.py              # DRF serializers for API
├── views.py                    # AgentViewSet + chat service patch
├── urls.py                     # Router registration
└── tests/
    ├── __init__.py
    └── test_tools.py           # 8 unit tests
```

## Key Classes

### `ToolRegistry` (singleton)

```python
from apps.agents.tools import get_tool_registry

registry = get_tool_registry()
tool = registry.get("search_notes")
tools = registry.list_tools()
metadata = registry.get_metadata("search_notes")
```

### `AgentOrchestrator`

```python
from apps.agents.services.orchestrator import AgentOrchestrator, AgentResult

orchestrator = AgentOrchestrator(
    max_iterations=5,
    max_tool_calls=10,
    request_timeout_seconds=60,
    per_tool_timeout_seconds=30,
)

result = orchestrator.run(
    user_request="Create 10 hard questions on my weak topics",
    user=request.user,
    session=chat_session,
    request_id="agent:abc123",
)
# AgentResult: answer, citations, tool_calls, iterations, tokens, latency, outcome, trace_id
```

### `StudyAIAgent`

```python
from apps.agents.services.agent import StudyAIAgent

agent = StudyAIAgent()
result = agent.process_request(
    user_request="What is backpropagation?",
    user=request.user,
    session=chat_session,
)
```

### `AgentExecutionLog`

```python
from apps.agents.models import AgentExecutionLog

log = AgentExecutionLog.objects.create(
    request_id="agent:abc123",
    profile=profile,
    intent_category="test_generation",
    model_provider="ollama",
    model_name="llama3.1:8b",
    prompt_version="agent_orchestrator:v1",
    tool_call_sequence=[...],
    iterations=3,
    retrieved_evidence_ids=["chunk-id-1", "chunk-id-2"],
    total_tokens=1500,
    total_latency_ms=2500,
    outcome="success",
    citation_verification_status="supported",
    guardrail_violations=0,
)
```

## Chat Service Integration

The existing `ChatService.ask()` now supports agent mode:

```python
# Classic RAG (default)
message = ChatService.ask(session, "What is X?")

# Agentic mode (with header or explicit flag)
message = ChatService.ask(session, "Create test on weak topics", use_agent=True)
```

The view checks for `X-Agent-Mode: true` header automatically.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agents/chat/` | Agentic chat with tool trace |
| GET | `/api/v1/agents/tools/` | List all tools with schemas |
| GET | `/api/v1/agents/executions/{request_id}/` | Execution trace |

### Request/Response Examples

**POST /agents/chat/**
```json
{
  "session_id": "uuid",
  "content": "Create 10 hard questions from my ML notes on weak topics"
}
```

```json
{
  "user": { "id": "...", "role": "user", "content": "...", "citations": [] },
  "assistant": {
    "id": "...",
    "role": "assistant",
    "content": "I've created a 10-question test...",
    "citations": [...],
    "tool_calls": [
      {
        "tool": "get_mastery",
        "arguments": { "subject_id": "uuid" },
        "result": { "tags": [...], "assessed_count": 5, "not_assessed_count": 2 },
        "latency_ms": 12,
        "success": true
      },
      {
        "tool": "search_notes",
        "arguments": { "query": "neural networks backpropagation", "subject_id": "uuid", "top_k": 8 },
        "result": { "results": [...], "query": "..." },
        "latency_ms": 245,
        "success": true
      },
      {
        "tool": "generate_questions",
        "arguments": { "document_id": "uuid", "count": 10, "difficulty": "hard" },
        "result": { "questions": [...], "test_id": null },
        "latency_ms": 1200,
        "success": true
      }
    ],
    "trace_id": "agent:session-uuid:abc123",
    "iterations": 3,
    "total_tokens": 2847,
    "total_latency_ms": 1457,
    "outcome": "success",
    "verification_status": "supported",
    "verification_score": 0.72
  }
}
```

## Settings

```python
# backend/config/settings/base.py

AGENT_ENABLED = True
AGENT_MAX_ITERATIONS = 5
AGENT_MAX_TOOL_CALLS = 10
AGENT_REQUEST_TIMEOUT_SECONDS = 60
AGENT_PER_TOOL_TIMEOUT_SECONDS = 30
AGENT_PROMPT_VERSION = "agent_orchestrator:v1"

AGENT_TOOL_TIMEOUTS = {
    "search_notes": 15,
    "search_reference_books": 15,
    "get_mastery": 5,
    "verify_evidence": 10,
    "get_document": 5,
    "get_subject_context": 5,
}
```

## Prometheus Metrics

```python
from shared.observability.metrics import (
    incr,
    # Agent-specific (added in telemetry.py)
)

# Auto-emitted by telemetry.record_agent_execution():
# agent_executions_total{outcome="success|partial|failed|limit_reached"}
# agent_tool_calls_total{tool="search_notes",success="true|false"}
# agent_iterations_histogram
# agent_tool_latency_seconds{tool="search_notes"}
# agent_token_usage_total{model="llama3.1:8b"}
```

## Adding a New Tool

1. Create `tools/new_category.py` with `BaseTool` subclass
2. Define `ToolInput`/`ToolOutput` Pydantic models
3. Add auto-registration at module bottom:
   ```python
   from apps.agents.tools import get_tool_registry
   get_tool_registry().register(MyNewTool())
   ```
4. Import in `tools/__init__.py`: `from apps.agents.tools import new_category`
4. Tool automatically appears in agent prompt and `/agents/tools/` endpoint

## Testing

```bash
# Run agent tests
docker compose run --rm api python -m pytest apps/agents/tests/ -v

# Run specific test
docker compose run --rm api python -m pytest apps/agents/tests/test_tools.py::TestSearchNotesTool -v

# With coverage
docker compose run --rm api python -m pytest apps/agents/tests/ --cov=apps.agents
```

## Extending for Phase 2+

### MCP Adapter (Phase 3)

```python
# apps/agents/mcp/adapter.py
class MCPToolAdapter:
    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry
    
    async def call_tool(self, name: str, args: dict, user_context) -> dict:
        tool = self.registry.get(name)
        input_model = tool.metadata.input_schema(**args)
        output = tool.execute(input_model, user=user_context.user, request_id=user_context.request_id)
        return output.model_dump()
```

### Artifact Tools (Phase 4)

```python
# tools/artifact.py
class GeneratePDFInput(ToolInput):
    outline: list[dict]
    evidence_ids: list[str]
    template: str = "default"

class GeneratePDFOutput(ToolOutput):
    file_id: str
    download_url: str
    page_count: int
```