# StudyAI Phase 8: Agentic/MCP Capabilities

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Created agentic LangGraph workflow with tool calling, guardrails, and MCP-compatible tool definitions

---

## 1. What Was Created

### 1.1 Agentic LangGraph Workflow

```
State: AgentState
  - user_request: str
  - profile_id: str
  - subject_id: str | None
  - session_id: str
  - retrieved_evidence: list[dict]
  - selected_evidence: list[dict]
  - answer: str
  - citations: list[dict]
  - verification_status: str
  - verification_score: float
  - tool_calls: list[dict]
  - iterations: int
  - max_iterations: int
  - max_tool_calls: int
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  analyze_request_node ──► select_tool_node ──► execute_tool_node
         ▲                                           │
         │                                           ▼
         └─────────────── (loop until limits) ────────┘
                                    │
                                    ▼
                              format_response_node ──► finalize_node ──► END
```

---

## 2. Files Modified/Created

| File | Change |
|------|--------|
| `ai/langgraph/state/agent_state.py` | **NEW** — `AgentState` TypedDict |
| `ai/langgraph/nodes/agent_nodes.py` | **NEW** — agent graph nodes |
| `ai/langgraph/graphs/agent_graph.py` | **NEW** — `StateGraph` with tool-calling loop |
| `tests/unit/test_agent_graph.py` | **NEW** — 9 unit tests for graph nodes and integration |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | LLM Call | Retries |
|------|---------|-------------------|----------|---------|
| `analyze_request_node` | Initialize state, list available tools | `studyai.agent.analyze` | No | 0 |
| `select_tool_node` | LLM decision: which tool to call or finalize | `studyai.agent.select_tool` | Yes | 0 |
| `execute_tool_node` | Execute selected tool with guardrails | `studyai.agent.execute_tool` | No | 0 |
| `format_response_node` | Generate response from tool results | `studyai.agent.format_response` | No | 0 |
| `finalize_node` | Prepare final state | `studyai.agent.finalize` | No | 0 |

---

## 4. Guardrails

| Guardrail | Default | Description |
|-----------|---------|-------------|
| `max_iterations` | 5 | Maximum LLM decision loops |
| `max_tool_calls` | 10 | Maximum tool executions per request |
| `request_timeout_seconds` | 60 | Wall-clock timeout (inherited from existing settings) |
| `per_tool_timeout_seconds` | 30 | Per-tool execution timeout (inherited) |

Branching logic after `execute_tool_node`:
- If `iterations >= max_iterations` OR `len(tool_calls) >= max_tool_calls` → `format_response_node`
- Otherwise → `select_tool_node` (continue loop)

---

## 5. MCP Tool Definitions

The existing tool registry (`apps/agents/tools/base.py`) already provides:
- Pydantic-validated input/output schemas
- Auth enforcement (`requires_auth`)
- Timeout configuration (`timeout_seconds`)
- Category grouping

The agentic graph consumes these directly via `get_tool_registry()`. MCP-compatible JSON Schema definitions are already generated in `apps/agents/mcp/registry.py`.

---

## 6. LangSmith Traces

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.agent` | chain | Full agent execution |
| `studyai.agent.analyze` | tool | Request analysis |
| `studyai.agent.select_tool` | tool | Tool selection (LLM call) |
| `studyai.agent.execute_tool` | tool | Tool execution |
| `studyai.agent.format_response` | tool | Response formatting |
| `studyai.agent.finalize` | tool | Finalization |

---

## 7. Preserved Behaviors

- **Tool registry** — same `BaseTool` + `ToolRegistry` pattern
- **Auth enforcement** — `requires_auth` checked per tool
- **Timeout handling** — per-tool timeouts preserved
- **Error handling** — tool failures logged, graceful degradation
- **Conversation context** — system prompt + user request preserved

---

## 8. New Behaviors

- **Typed state:** Explicit `AgentState` TypedDict
- **Graph-based loop:** LangGraph conditional edges replace custom `while` loop
- **Observability:** Graph execution visible in LangSmith as `studyai.agent`
- **Tool call tracking:** `tool_calls` list in state for full audit trail

---

## 9. Tests

### New Tests (9 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_agent_graph.py` | Node unit tests, graph build, conditional branching, guardrails |

### Existing Tests (65 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_learning_features.py` | Agent workflow evaluation tests |

---

## 10. Validation

- 89/89 total tests pass
- All existing agent workflow tests pass
- Graph builds and executes correctly
- Guardrails enforce max iterations and max tool calls
- LangSmith client initialized successfully

---

## 11. Next Steps

1. Validate LangSmith traces in production
2. Consider migrating `AgentOrchestrator.run()` to use the new graph
3. Add more agentic workflows (e.g., multi-step research, document analysis)
