# StudyAI Phase 4: Question Generation Migration

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Migrated `QuestionGenerationService.generate_for_document` from sequential loop to LangGraph workflow

---

## 1. What Was Migrated

### 1.1 Original Flow

```
Document chunks (max_questions)
    ↓
For each chunk:
  LLM structured output (question_generation prompt)
    ↓
  Compute question_key + content_hash
    ↓
  get_or_create Question (idempotent)
    ↓
  Link to tag if exists
```

### 1.2 New LangGraph Flow

```
State: QuestionGenerationState
  - document_id: str
  - chunks: list[dict]
  - questions: list[dict]
  - validated_questions: list[dict]
  - verified_questions: list[dict]
  - persisted_questions: list[dict]
  - max_questions: int
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  retrieve_chunks_node ──────────────────► (on error) ─► error_node ─► END
    │
    ▼
  generate_questions_node ───────────────► (on error) ─► error_node ─► END
    │
    ▼
  validate_questions_node
    │
    ├── invalid questions ───────────────┐
    │                                    ▼
    │                            persist_questions_node ─► END
    │                                    ▲
    └── valid questions ──► verify_evidence_node ──────────┘
```

---

## 2. Files Modified/Created

| File | Change |
|------|--------|
| `apps/questions/question_generation_nodes.py` | **NEW** — graph node implementations |
| `ai/langgraph/state/question_generation_state.py` | **NEW** — `QuestionGenerationState` TypedDict |
| `ai/langgraph/graphs/question_generation_graph.py` | **NEW** — `StateGraph` definition with conditional branching |
| `apps/questions/services.py` | `generate_for_document` now invokes `invoke_question_generation_graph()` |
| `tests/unit/test_question_generation_graph.py` | **NEW** — 9 unit tests for graph nodes and integration |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | LLM Call | Retries |
|------|---------|-------------------|----------|---------|
| `retrieve_chunks_node` | Fetch active chunks from document | `studyai.question_generation.retrieve` | No | 0 |
| `generate_questions_node` | LLM structured output per chunk | `studyai.question_generation.generate` | Yes | 0 |
| `validate_questions_node` | Validate question structure | `studyai.question_generation.validate` | No | 0 |
| `verify_evidence_node` | Deterministic `EvidenceVerifier._classify` | `studyai.question_generation.verify` | No | 0 |
| `persist_questions_node` | get_or_create Questions + tag links | `studyai.question_generation.persist` | No | 0 |

---

## 4. Conditional Branching

After `validate_questions_node`:
- If any questions fail validation → skip verification, go directly to `persist_questions_node`
- If all questions are valid → proceed to `verify_evidence_node`, then `persist_questions_node`

This avoids unnecessary verification calls for malformed questions.

---

## 5. Preserved Behaviors

- **Idempotency** — `get_or_create` with `source_revision_id`, `content_hash`, `question_key` unchanged
- **Tag linking** — `QuestionTagLink` creation via `_primary_tag(document)` unchanged
- **Prompt version tracking** — `question_generation:v1` stored on each question
- **Provider abstraction** — `get_llm_provider()` still the application boundary
- **Transaction atomicity** — `@transaction.atomic` preserved on service method
- **Deterministic hashing** — `_question_key()`, `_content_hash()` logic preserved in node
- **Max questions limit** — `max_questions` parameter preserved

---

## 6. New Behaviors

- **LangSmith tracing:** Every node execution and LLM call traced as `studyai.question_generation.*`
- **Typed state:** Explicit `QuestionGenerationState` TypedDict
- **Validation branching:** Invalid questions skip evidence verification
- **Observability:** Graph execution visible in LangSmith as `studyai.question_generation`

---

## 7. LangSmith Traces

When `LANGSMITH_TRACING=true`, you'll see:

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.question_generation` | chain | Full graph execution |
| `studyai.question_generation.retrieve` | tool | Chunk retrieval |
| `studyai.question_generation.generate` | tool | LLM question generation |
| `studyai.question_generation.validate` | tool | Question validation |
| `studyai.question_generation.verify` | tool | Evidence verification |
| `studyai.question_generation.persist` | tool | DB persistence |
| `studyai.llm.question_generation` | llm | Individual LLM call |

---

## 8. Tests

### New Tests (9 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_question_generation_graph.py` | Node unit tests, graph build, conditional branching |

### Existing Tests

No existing tests were broken by this migration.

---

## 9. Validation

- 42/42 total new unit tests pass (foundation + chat + enrichment + question generation)
- Graph builds and executes correctly
- Conditional branching works (invalid questions skip verification)
- LangSmith client initialized successfully

---

## 10. Next Steps

1. Validate LangSmith traces in production
2. Proceed to **Phase 5: Citation/Evidence Verification Graph** (extract verification into reusable sub-graph)
