# StudyAI Phase 2: Ask StudyAI (Chat) Migration

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Migrated `ChatService._ask_classic` from inline RAG to LangGraph workflow

---

## 1. What Was Migrated

### 1.1 Original Flow

```
User Question
    ↓
RetrievalService.search(profile, query, subject, top_k=4)
    ↓
LLM.generate_structured(Prompt(name="chat", version="v1", user="EVIDENCE_JSON:" + json.dumps(payload)))
    ↓
Parse answer + cited_chunk_ids
    ↓
EvidenceVerifier._classify(answer, cited_contents)
    ↓
Persist ChatMessage with citations + verification status
```

### 1.2 New LangGraph Flow

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
  - retry_count: int
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  retrieve_node ──────────────────► (on error) ─► error_node ─► END
    │
    ▼
  evidence_selection_node
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

---

## 2. Files Modified

| File | Change |
|------|--------|
| `apps/chat/services.py` | `_ask_classic` now invokes `invoke_chat_graph()` instead of inline retrieval + LLM call |
| `apps/chat/langgraph_nodes.py` | **NEW** — graph node implementations |
| `ai/langgraph/state/chat_state.py` | **NEW** — `ChatState` TypedDict |
| `ai/langgraph/graphs/chat_graph.py` | **NEW** — `StateGraph` definition with conditional branching |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | Retries |
|------|---------|-------------------|---------|
| `retrieve_node` | Hybrid retrieval scoped to profile/subject | `studyai.chat.retrieve` | 0 |
| `evidence_selection_node` | Pass-through (future: re-rank/filter) | `studyai.chat.select_evidence` | 0 |
| `answer_generation_node` | LLM structured output with `ChatAnswer` schema | `studyai.chat.generate` | 1 |
| `citation_verification_node` | Deterministic `EvidenceVerifier._classify` | `studyai.chat.verify` | 0 |
| `retry_answer_node` | Regenerate answer with verification feedback | `studyai.chat.retry` | 0 |
| `format_response_node` | Prepare final output for persistence | `studyai.chat.format` | 0 |

---

## 4. Preserved Behaviors

- Profile/subject scoping (enforced in `RetrievalService.search`)
- Hybrid retrieval (dense + keyword + RRF)
- Revision awareness (chunks carry `revision_ids`)
- Citation verification (deterministic `EvidenceVerifier`)
- Prompt version tracking (`CHAT_PROMPT_VERSION = "chat:v1"`)
- API contract (same `ChatMessage` response shape)
- Budget enforcement (`assert_within_budget` in `ask()`)

---

## 5. New Behaviors

- **Retry on unsupported citations:** If `EvidenceVerifier` returns `unsupported`, the graph retries once with feedback
- **LangSmith tracing:** Every node execution, LLM call, and retrieval operation is traced
- **Typed state:** Explicit `ChatState` TypedDict replaces ad-hoc dict passing
- **Observability:** Graph execution is visible in LangSmith as `studyai.chat.classic`

---

## 6. Integration Point

```python
# apps/chat/services.py
def _ask_classic(session: ChatSession, content: str) -> ChatMessage:
    from ai.langgraph.graphs.chat_graph import invoke_chat_graph
    from ai.langgraph.state.chat_state import ChatState

    initial_state = ChatState(
        user_request=content,
        profile_id=str(session.profile_id),
        subject_id=str(session.subject_id) if session.subject_id else None,
        session_id=str(session.pk),
        ...
    )

    final_state = invoke_chat_graph(initial_state)
    return _persist_chat_message(session, final_state)
```

---

## 7. Tests

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_chat_graph.py` | Node unit tests, graph build, branching logic |
| `tests/api/test_learning_features.py` (existing) | `ChatTests.test_chat_flow_grounds_and_cites` — validates end-to-end behavior |

---

## 8. Validation

- All Python files pass syntax validation
- Existing chat API tests should continue to pass (same response shape)
- LangSmith traces visible when `LANGSMITH_TRACING=true`

---

## 9. Next Steps

1. Run `python manage.py test tests.api.test_learning_features.ChatTests` to validate end-to-end
2. Enable `LANGSMITH_TRACING=true` in `.env` and verify traces in LangSmith UI
3. Proceed to **Phase 3: AI Enrichment Migration**
