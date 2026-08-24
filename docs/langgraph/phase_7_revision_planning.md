# StudyAI Phase 7: Revision Planning Migration

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Migrated `RevisionPlanningService.build_plan` from direct service call to LangGraph workflow

---

## 1. What Was Migrated

### 1.1 Original Flow

```
RevisionPlanningService.build_plan(profile, subject, target_date):
    1. Compute days_left, horizon (max 14 days)
    2. For each candidate tag:
       - Get mastery score
       - Compute weakness = (1 - mastery) if assessed else 0.55
       - Compute urgency = min(1.0, days_left / 14)
       - Count recent failures (last 14 days)
       - Compute insufficient = 1.0 if not assessed else 0.0
       - priority = 0.45*weakness + 0.25*urgency + 0.20*failures + 0.10*insufficient
    3. Sort by (-priority, display_name)
    4. Build 2-sessions-per-day schedule
    5. Return priorities + schedule
```

### 1.2 New LangGraph Flow

```
State: RevisionPlanningState
  - profile_id: str
  - subject_id: str | None
  - target_date: str
  - days_left: int
  - horizon: int
  - weights: dict
  - urgency: float
  - candidates: list[dict]
  - priorities: list[dict]
  - schedule: list[dict]
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  get_mastery_overview_node ──► build_plan_node ──► format_output_node ──► END
```

---

## 2. Files Modified/Created

| File | Change |
|------|--------|
| `apps/revision/revision_planning_nodes.py` | **NEW** — graph node implementations |
| `ai/langgraph/state/revision_planning_state.py` | **NEW** — `RevisionPlanningState` TypedDict |
| `ai/langgraph/graphs/revision_planning_graph.py` | **NEW** — `StateGraph` definition |
| `apps/revision/views.py` | `RevisionPlansView.get()` now invokes `invoke_revision_planning_graph()` |
| `tests/unit/test_revision_planning_graph.py` | **NEW** — 4 unit tests for graph nodes and integration |

---

## 3. Node Specifications

| Node | Purpose | LangSmith Run Name | LLM Call | Retries |
|------|---------|-------------------|----------|---------|
| `get_mastery_overview_node` | Fetch mastery overview via `RevisionPlanningService.overview()` | `studyai.revision_planning.overview` | No | 0 |
| `build_plan_node` | Build deterministic plan via `RevisionPlanningService.build_plan()` | `studyai.revision_planning.build` | No | 0 |
| `format_output_node` | Prepare final output for API response | `studyai.revision_planning.format` | No | 0 |

---

## 4. Preserved Behaviors

- **Deterministic priority scoring** — same weights (0.45 weakness, 0.25 urgency, 0.20 failures, 0.10 insufficient)
- **Mastery thresholds** — WEAK=0.4, STRONG=0.8 unchanged
- **Schedule generation** — 2 sessions per day, max 14 days horizon
- **Subject scoping** — optional subject filter preserved
- **Recency window** — 14-day failure window preserved
- **Tie-breaking** — sorted by (-priority, display_name) unchanged

---

## 5. New Behaviors

- **LangSmith tracing:** Every node execution traced as `studyai.revision_planning.*`
- **Typed state:** Explicit `RevisionPlanningState` TypedDict
- **Observability:** Graph execution visible in LangSmith as `studyai.revision_planning`

---

## 6. LangSmith Traces

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.revision_planning` | chain | Full graph execution |
| `studyai.revision_planning.overview` | tool | Mastery overview retrieval |
| `studyai.revision_planning.build` | tool | Plan building |
| `studyai.revision_planning.format` | tool | Output formatting |

---

## 7. Tests

### New Tests (4 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_revision_planning_graph.py` | Node unit tests, graph build |

### Existing Tests (65 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_learning_features.py` | Revision planner API tests |

---

## 8. Validation

- 89/89 total tests pass
- All existing revision planner API tests pass
- Graph builds and executes correctly
- LangSmith client initialized successfully

---

## 9. Next Steps

1. Proceed to **Phase 8: Agentic/MCP Capabilities**
