# StudyAI Phase 6: Adaptive Tests Migration

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Migrated `MasteryAwareTestGenerationTool` from inline imperative code to LangGraph workflow

---

## 1. What Was Migrated

### 1.1 Original Flow

```
MasteryAwareTestGenerationTool._execute():
    1. Get mastery overview (RevisionPlanningService.overview)
    2. Identify weak tags (filter by status, subject)
    3. Search notes for weak topics (RetrievalService.search per tag)
    4. Generate questions from found documents (QuestionGenerationService.generate_for_document)
    5. Filter by difficulty, select top N
    6. Create TestInstance + TestQuestion rows
```

### 1.2 New LangGraph Flow

```
State: AdaptiveTestState
  - profile_id: str
  - subject_id: str | None
  - num_questions: int
  - difficulty: str | None
  - focus_weak_only: bool
  - mastery_overview: dict
  - weak_tags: list[dict]
  - all_tags: list[dict]
  - retrieved_document_ids: list[str]
  - generated_questions: list[dict]
  - selected_questions: list[dict]
  - test_id: str | None
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  get_mastery_node ──────────────────► (on error) ─► END
    │
    ▼
  identify_weak_topics_node ────────► (ValueError if no topics) ─► END
    │
    ▼
  retrieve_notes_node ───────────────► (on error) ─► END
    │
    ▼
  generate_questions_node ───────────► (on error) ─► END
    │
    ▼
  select_questions_node
    │
    ▼
  create_test_node ──────────────────► (on error) ─► END
    │
    ▼
  format_output_node ────────────────► END
```

---

## 2. Files Modified/Created

| File | Change |
|------|--------|
| `apps/tests/adaptive_test_nodes.py` | **NEW** — graph node implementations |
| `ai/langgraph/state/adaptive_test_state.py` | **NEW** — `AdaptiveTestState` TypedDict |
| `ai/langgraph/graphs/adaptive_test_graph.py` | **NEW** — `StateGraph` definition |
| `apps/agents/tools/learning.py` | `MasteryAwareTestGenerationTool._execute()` now invokes graph |
| `tests/unit/test_adaptive_test_graph.py` | **NEW** — 11 unit tests for graph nodes and integration |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | LLM Call | Retries |
|------|---------|-------------------|----------|---------|
| `get_mastery_node` | Fetch mastery overview via `RevisionPlanningService.overview()` | `studyai.adaptive_test.mastery` | No | 0 |
| `identify_weak_topics_node` | Filter weak/not_assessed tags, fallback to assessed | `studyai.adaptive_test.identify_weak` | No | 0 |
| `retrieve_notes_node` | Search notes for each weak topic via `RetrievalService.search()` | `studyai.adaptive_test.retrieve` | No | 0 |
| `generate_questions_node` | Generate questions via `QuestionGenerationService.generate_for_document()` | `studyai.adaptive_test.generate` | Yes | 0 |
| `select_questions_node` | Filter by difficulty, select top N | `studyai.adaptive_test.select` | No | 0 |
| `create_test_node` | Create `TestInstance` + `TestQuestion` rows | `studyai.adaptive_test.create_test` | No | 0 |
| `format_output_node` | Prepare final output for tool response | `studyai.adaptive_test.format` | No | 0 |

---

## 4. Preserved Behaviors

- **Mastery-aware selection** — `RevisionPlanningService.overview()` unchanged
- **Weak topic fallback** — if no weak/not_assessed tags, falls back to all assessed tags
- **Retrieval scoping** — `RetrievalService.search()` with subject filter, top_k=5
- **Question generation** — delegates to Phase 4 `QuestionGenerationService.generate_for_document()` (LangGraph)
- **Difficulty filtering** — filters generated questions by difficulty, falls back to all if insufficient
- **Test creation** — `TestInstance` + `TestQuestion` creation in `transaction.atomic()`
- **Error handling** — `ValueError` raised when no topics or no documents available
- **Agent tool contract** — `MasteryAwareTestOutput` schema unchanged

---

## 5. New Behaviors

- **LangSmith tracing:** Every node execution traced as `studyai.adaptive_test.*`
- **Typed state:** Explicit `AdaptiveTestState` TypedDict
- **Observability:** Graph execution visible in LangSmith as `studyai.adaptive_test`
- **Reuses Phase 4 graph:** `QuestionGenerationService.generate_for_document()` invokes question generation LangGraph internally

---

## 6. LangSmith Traces

When `LANGSMITH_TRACING=true`, you'll see:

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.adaptive_test` | chain | Full graph execution |
| `studyai.adaptive_test.mastery` | tool | Mastery overview retrieval |
| `studyai.adaptive_test.identify_weak` | tool | Weak topic identification |
| `studyai.adaptive_test.retrieve` | tool | Note retrieval for weak topics |
| `studyai.adaptive_test.generate` | tool | Question generation (calls Phase 4 graph) |
| `studyai.adaptive_test.select` | tool | Question selection/filtering |
| `studyai.adaptive_test.create_test` | tool | Test instance creation |
| `studyai.adaptive_test.format` | tool | Output formatting |

---

## 7. Tests

### New Tests (11 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_adaptive_test_graph.py` | Node unit tests, graph build, conditional branching |

### Existing Tests (65 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_ai_classroom.py` | Enrichment API tests |
| `tests/api/test_learning_features.py` | Adaptive tests, mastery, tagging, chat, revision planner |

---

## 8. Validation

- 76/76 total tests pass (11 new + 65 existing)
- All enrichment API tests pass
- All learning feature API tests pass
- Graph builds and executes correctly
- Questions are generated and persisted correctly
- LangSmith client initialized successfully

---

## 9. Bug Fix: Phase 4 Question Generation State Key

During Phase 6 testing, discovered a bug in Phase 4's `question_generation_graph.py`:
- `_run_verification` was reading from `state.get("verified_questions", [])` instead of `state.get("validated_questions", [])`
- This caused 0 questions to be persisted because the verification node had no input
- Fixed by changing to `validated_questions` in `ai/langgraph/graphs/question_generation_graph.py:23`

---

## 10. Next Steps

1. Validate LangSmith traces in production
2. Proceed to **Phase 7: Revision Planning** (if agentic behavior added) or **Phase 8: Agentic/MCP Capabilities**
