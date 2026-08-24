# StudyAI Agent Architecture

## Overview

The StudyAI Agent is an orchestration layer that transforms the fixed RAG chatbot into an extensible agentic interface. It reasons about user requests, selects appropriate tools, executes multi-step workflows, and produces grounded responses.

## Core Principles

1. **No Business Logic Duplication** — Agent ONLY orchestrates; all domain logic stays in existing services
2. **Strong Typing** — Every tool has Pydantic input/output schemas
3. **Security by Default** — Auth at tool layer, RLS at DB layer, schema validation everywhere
4. **Observability First** — Full execution trace, metrics, structured logging
5. **Deterministic Boundaries** — LLM decides WHICH tools; services decide HOW

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
│  POST /agents/chat/  |  GET /agents/tools/  |  GET /agents/executions/      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           StudyAIAgent                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ AgentOrchestrator                                                    │    │
│  │  - max_iterations: 5                                                │    │
│  │  - max_tool_calls: 10                                               │    │
│  │  - request_timeout: 60s                                             │    │
│  │  - run(request, user, session) -> AgentResult                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Tool Registry                                       │
│  Tool(name, description, input_schema, output_schema, auth, timeout)        │
│  Registered: search_notes, search_reference_books, get_mastery,             │
│              verify_evidence, get_document, get_subject_context             │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Retrieval Tools    │ │  Learning Tools │ │  Evidence Tools │
│  - SearchNotesTool  │ │  - GetMastery   │ │  - VerifyEvidence│
│  - SearchRefBooks   │ │  (future: more) │ │                  │
└─────────────────────┘ └─────────────────┘ └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Existing Domain Services                                 │
│  RetrievalService | EvidenceVerifier | RevisionPlanningService |            │
│  MasteryScoringService | QuestionGenerationService | TestGenerationService  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PostgreSQL / pgvector / Redis / Celery                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Agent Orchestration Loop

```python
def run(self, user_request: str, user, session) -> AgentResult:
    trace_id = generate_request_id()
    tool_calls = []
    iterations = 0
    
    while iterations < self.max_iterations:
        iterations += 1
        
        # 1. LLM decides next action (tool or final answer)
        decision = self._llm_decide(user_request, tool_calls, available_tools)
        
        if decision.is_final_answer:
            # 2. Verify evidence for final answer
            verified = self._verify_final_answer(decision.answer, decision.citations)
            return AgentResult(answer=decision.answer, citations=verified, tool_calls, trace_id)
        
        # 3. Execute selected tool
        tool = self.registry.get(decision.tool_name)
        tool_result = tool.execute(decision.tool_args, user=user, request_id=trace_id)
        
        # 4. Record tool call for trace
        tool_calls.append(ToolCallRecord(
            tool=decision.tool_name,
            args=decision.tool_args,
            result=tool_result,
            latency_ms=tool_result.latency_ms,
            success=tool_result.success
        ))
        
        # 5. Check limits
        if len(tool_calls) >= self.max_tool_calls:
            break
    
    # Graceful degradation: return best effort with trace
    return AgentResult(answer=partial_answer, citations=[], tool_calls, trace_id, outcome="limit_reached")
```

## Tool Interface Contract

### Base Classes
```python
class ToolInput(BaseModel):
    """All tool inputs inherit from this — enables schema validation."""
    pass

class ToolOutput(BaseModel):
    """All tool outputs inherit from this — enables schema validation."""
    success: bool = True
    error: str | None = None
    latency_ms: int = 0

@dataclass
class ToolMetadata:
    name: str
    description: str
    input_schema: type[ToolInput]
    output_schema: type[ToolOutput]
    requires_auth: bool = True
    timeout_seconds: int = 30
    category: str = "general"  # retrieval | learning | evidence | document

class Tool(Protocol):
    metadata: ToolMetadata
    
    def execute(self, input: ToolInput, *, user, request_id: str) -> ToolOutput:
        """Execute tool with auth, validation, timeout, telemetry."""
        ...
```

### Tool Execution Flow
```
Tool.execute(input, user, request_id)
    │
    ├─► Validate input against input_schema (Pydantic)
    │
    ├─► ProfileAuthorizationService.ensure_profile_access(user, profile)
    │
    ├─► Execute domain service method (scoped to profile)
    │
    ├─► Validate output against output_schema (Pydantic)
    │
    ├─► Record telemetry (latency, success, error)
    │
    └─► Return ToolOutput
```

## Security Boundaries

| Layer | Protection |
|-------|------------|
| **Agent** | Only sees registered tools; no dynamic tool invocation |
| **Tool** | Pydantic schema validation on all inputs/outputs |
| **Tool** | `ProfileAuthorizationService` enforces profile ownership |
| **Service** | Domain services use profile-scoped queries only |
| **Database** | Row-Level Security (RLS) as final defense |
| **LLM** | Prompt-injection directive + PII sanitization in provider chain |
| **Budget** | `assert_within_budget(profile_id)` before any LLM call |

## Data Flow: User Request → Final Response

```
1. User sends "Create 10 hard questions from my ML notes on weak topics"
    │
2. AgentChatViewSet receives request
    │
3. StudyAIAgent.process_request()
    │
4. Orchestrator iteration 1:
    │   LLM: "Need to find weak topics first → get_mastery"
    │   Tool: GetMasteryTool.execute(subject="ML")
    │   Result: [{tag: "neural_networks", mastery: 0.3}, {tag: "transformers", mastery: 0.2}]
    │
5. Orchestrator iteration 2:
    │   LLM: "Weak topics: neural_networks, transformers → search_notes"
    │   Tool: SearchNotesTool.execute(query="neural networks transformers", subject="ML")
    │   Result: [Evidence(chunk_id=..., content="backpropagation..."), ...]
    │
6. Orchestrator iteration 3:
    │   LLM: "Have evidence, weak topics → generate_questions"
    │   Tool: GenerateQuestionsTool.execute(document_ids=[...], count=10, difficulty="hard")
    │   Result: [Question(id=..., prompt="...", options=[...], answer_index=2), ...]
    │
7. Orchestrator iteration 4:
    │   LLM: "Questions generated → create_test"
    │   Tool: CreateTestTool.execute(subject="ML", num_questions=10)
    │   Result: TestInstance(id=..., test_questions=[...])
    │
8. Orchestrator iteration 5:
    │   LLM: "Test created → final answer"
    │   Decision: is_final_answer=True
    │
9. EvidenceVerifier.verify() on final answer citations
    │
10. ChatMessage persisted with tool_calls trace
    │
11. Response returned to frontend with tool_calls for UI display
```

## Telemetry Schema

### AgentExecutionLog (Database)
```sql
CREATE TABLE agents_agentexecutionlog (
    id UUID PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    profile_id UUID REFERENCES profiles_profile(id),
    intent_category VARCHAR(32),
    model_provider VARCHAR(64),
    model_name VARCHAR(128),
    prompt_version VARCHAR(64),
    tool_call_sequence JSONB NOT NULL DEFAULT '[]',
    iterations INTEGER DEFAULT 0,
    retrieved_evidence_ids JSONB DEFAULT '[]',
    total_tokens INTEGER DEFAULT 0,
    total_latency_ms INTEGER DEFAULT 0,
    outcome VARCHAR(16),  -- success | partial | failed | limit_reached
    citation_verification_status VARCHAR(24),
    guardrail_violations INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_agent_log_request ON agents_agentexecutionlog(request_id);
CREATE INDEX idx_agent_log_profile ON agents_agentexecutionlog(profile_id);
CREATE INDEX idx_agent_log_created ON agents_agentexecutionlog(created_at);
```

### Prometheus Metrics
```python
agent_executions_total{outcome="success|partial|failed|limit_reached"}
agent_tool_calls_total{tool="search_notes",success="true|false"}
agent_iterations_histogram
agent_tool_latency_seconds{tool="search_notes"}
agent_token_usage_total{model="llama3.1:8b"}
```

### Structured Log Format
```
agent.iteration request_id=abc123 iteration=1 tool=search_notes args_hash=sha256 
    latency_ms=245 success=true evidence_count=4 weak_topics=2
agent.iteration request_id=abc123 iteration=2 tool=get_mastery args_hash=sha256
    latency_ms=12 success=true tags_assessed=15
agent.complete request_id=abc123 iterations=3 tools=2 tokens=1847 latency_ms=892
    outcome=success verification=supported guardrails=0
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `AGENT_MAX_ITERATIONS` | 5 | Max reasoning loops per request |
| `AGENT_MAX_TOOL_CALLS` | 10 | Max total tool invocations |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | 60 | Wall-clock timeout for full request |
| `AGENT_PER_TOOL_TIMEOUT_SECONDS` | 30 | Per-tool execution timeout |
| `AGENT_TOOL_TIMEOUTS` | {} | Per-tool override (seconds) |
| `AGENT_ENABLED` | true | Feature flag |
| `AGENT_PROMPT_VERSION` | "agent_orchestrator:v1" | System prompt version |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Tool schema validation fails | Return ToolOutput(success=False, error="..."); agent decides retry/continue |
| Tool execution timeout | Return ToolOutput(success=False, error="timeout"); count toward limits |
| Auth failure (Forbidden) | Return ToolOutput(success=False, error="forbidden"); agent stops |
| LLM provider failure | Provider chain fallback (existing); if all fail, return error |
| Max iterations reached | Return partial answer with `outcome="limit_reached"` |
| Max tool calls reached | Return partial answer with `outcome="limit_reached"` |
| Evidence verification fails | Log warning; include unverified citations with status |

## Future Extensibility

### Adding New Tools
1. Create `NewTool` in `tools/{category}.py` extending `Tool` protocol
2. Define `NewToolInput` / `NewToolOutput` Pydantic models
3. Register in `ToolRegistry` at module import
4. Add to agent prompt template (auto-injected from registry metadata)
5. Write unit tests

### MCP Adapter (Phase 3)
```python
# MCP Adapter translates MCP protocol → internal Tool execution
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
- `generate_pdf` — Input: outline + evidence → Output: file_id (MinIO)
- `generate_pptx` — Input: outline + evidence → Output: file_id
- `generate_docx` — Input: outline + evidence → Output: file_id
- All follow same tool interface; agent discovers them automatically