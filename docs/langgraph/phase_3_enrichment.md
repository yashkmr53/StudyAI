# StudyAI Phase 3: AI Enrichment Migration

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Migrated `run_enrichment_job` from sequential pipeline to LangGraph workflow

---

## 1. What Was Migrated

### 1.1 Original Flow

```
Document
    ↓
Retrieve user chunks + reference chunks
    ↓
LLM Draft (schema-validated)
    ↓
LLM Gap Detection (schema-validated)
    ↓
LLM Gap Filling (schema-validated)
    ↓
Citation Stitching + Evidence Verification (deterministic)
    ↓
Persist EnrichedNote / Blocks / Citations
```

### 1.2 New LangGraph Flow

```
State: EnrichmentState
  - document_id: str
  - job_id: str
  - user_chunks: list[dict]
  - reference_chunks: list[dict]
  - evidence_payload: dict
  - draft_result: dict
  - gaps_result: dict
  - fill_result: dict
  - all_blocks: list[dict]
  - stitched_blocks: list[dict]
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  retrieve_chunks_node ──────────────────► (on error) ─► error_node ─► END
    │
    ▼
  draft_node ────────────────────────────► (on error) ─► error_node ─► END
    │
    ▼
  gap_detection_node ────────────────────► (on error) ─► error_node ─► END
    │
    ▼
  ┌─────────────────────────────────────┐
  │ Conditional: gaps exist?            │
  └─────────────────────────────────────┘
    │ yes                    │ no
    ▼                       ▼
  gap_fill_node       citation_stitch_node
    │                       │
    └───────────┬───────────┘
                ▼
    evidence_verification_node
                │
                ▼
          format_output_node
                │
                ▼
                END
```

---

## 2. Files Modified/Created

| File | Change |
|------|--------|
| `apps/ai_classroom/enrichment_nodes.py` | **NEW** — graph node implementations |
| `ai/langgraph/state/enrichment_state.py` | **NEW** — `EnrichmentState` TypedDict |
| `ai/langgraph/graphs/enrichment_graph.py` | **NEW** — `StateGraph` definition with conditional branching |
| `apps/ai_classroom/services.py` | `run_enrichment_job` now invokes `invoke_enrichment_graph()` |
| `tests/unit/test_enrichment_graph.py` | **NEW** — 11 unit tests for graph nodes and integration |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | LLM Call | Retries |
|------|---------|-------------------|----------|---------|
| `retrieve_chunks_node` | Fetch user + reference chunks | `studyai.enrichment.retrieve` | No | 0 |
| `draft_node` | LLM structured output with `enrichment_draft` prompt | `studyai.enrichment.draft` | Yes | 0 |
| `gap_detection_node` | LLM structured output with `gap_detection` prompt | `studyai.enrichment.gap_detection` | Yes | 0 |
| `gap_fill_node` | LLM structured output with `gap_filling` prompt | `studyai.enrichment.gap_fill` | Yes | 0 |
| `citation_stitch_node` | Combine blocks with source refs | `studyai.enrichment.stitch` | No | 0 |
| `evidence_verification_node` | Deterministic `EvidenceVerifier.verify` | `studyai.enrichment.verify` | No | 0 |
| `format_output_node` | Prepare final state for persistence | `studyai.enrichment.format` | No | 0 |

---

## 4. Conditional Branching

After `gap_detection_node`:
- If `gaps_result.data["gaps"]` is non-empty → proceed to `gap_fill_node`
- If `gaps_result.data["gaps"]` is empty → skip `gap_fill_node`, go directly to `citation_stitch_node`

This is a genuine improvement over the previous linear flow where gap filling always ran even when no gaps were detected.

---

## 5. Preserved Behaviors

- **EvidenceVerifier** — deterministic rule-based verification unchanged (`EvidenceVerifier.verify`, `EvidenceVerifier._classify`)
- **PromptVersion tracking** — `active_prompt("enrichment_draft")`, etc. from DB-backed `PromptVersion`
- **Schema validation** — `validate_stage_output()` per stage
- **Staleness propagation** — handled by existing job/index infrastructure
- **Coalescing** — handled by existing `Job` model and `dispatch_job`
- **Budget enforcement** — `assert_within_budget` in `enqueue_enrichment`
- **Provider abstraction** — `get_llm_provider()` still the application boundary
- **Celery integration** — `run_enrichment_job(job: Job)` signature unchanged
- **Persistence** — exact same `EnrichedNote`, `EnrichedNoteBlock`, `CitationBlock` creation logic
- **Learning hooks** — `TaggingService` and `QuestionGenerationService` calls unchanged

---

## 6. New Behaviors

- **LangSmith tracing:** Every node execution, LLM call, and retrieval operation is traced as `studyai.enrichment.*`
- **Typed state:** Explicit `EnrichmentState` TypedDict replaces ad-hoc dict passing
- **Observability:** Graph execution is visible in LangSmith as `studyai.enrichment`
- **Conditional gap filling:** Skips gap fill step when no gaps are detected

---

## 7. LangSmith Traces

When `LANGSMITH_TRACING=true`, you'll see:

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.enrichment` | chain | Full graph execution |
| `studyai.enrichment.retrieve` | tool | Chunk retrieval |
| `studyai.enrichment.draft` | tool | Draft LLM call |
| `studyai.enrichment.gap_detection` | tool | Gap detection LLM call |
| `studyai.enrichment.gap_fill` | tool | Gap fill LLM call (conditional) |
| `studyai.enrichment.stitch` | tool | Citation stitching |
| `studyai.enrichment.verify` | tool | Evidence verification |
| `studyai.enrichment.format` | tool | Output formatting |
| `studyai.llm.enrichment_draft` | llm | Individual LLM call tracing |
| `studyai.llm.gap_detection` | llm | Individual LLM call tracing |
| `studyai.llm.gap_filling` | llm | Individual LLM call tracing |

---

## 8. Tests

### New Tests (11 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_enrichment_graph.py` | Node unit tests, graph build, conditional branching |

### Existing Tests (9 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_ai_classroom.py` | End-to-end enrichment, verification, staleness, refresh, prompt registry |

---

## 9. Validation

- All 33 unit tests pass
- All 9 existing enrichment API tests pass
- Graph builds and executes correctly
- Conditional branching works (gap fill skipped when no gaps)
- LangSmith client initialized successfully in test environment

---

## 10. Known Issues

1. **LangSmith `project_name` parameter:** The installed `langsmith` v0.11.1 does not accept `project_name` in `Client.__init__()`. Fixed by passing `project_name` to `create_run()` instead.
2. **`create_run()` returns `None`:** In langsmith v0.11.1, `create_run()` may return `None` (async batching). Decorators handle this gracefully.
3. **Test isolation:** Container environment has `LANGSMITH_TRACING=true`, requiring explicit env var mocking in unit tests.

---

## 11. Next Steps

1. Validate LangSmith traces in production with real LLM calls
2. Proceed to **Phase 4: Question Generation** migration
