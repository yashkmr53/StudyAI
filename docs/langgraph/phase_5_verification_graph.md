# StudyAI Phase 5: Citation/Evidence Verification Graph

**Date:** 2026-08-24  
**Status:** Complete  
**Scope:** Extracted evidence verification into reusable LangGraph sub-graph used by chat, enrichment, and question generation

---

## 1. What Was Created

### 1.1 Reusable Verification Sub-Graph

```
State: VerificationState
  - content: str
  - cited_contents: list[str]
  - verification_status: str
  - verification_score: float
  - errors: list[str]
  - execution_metadata: dict

Graph:
  START
    │
    ▼
  verify_node ──► END
```

### 1.2 Files Created

| File | Purpose |
|------|---------|
| `ai/langgraph/state/verification_state.py` | `VerificationState` TypedDict |
| `ai/langgraph/nodes/verification_nodes.py` | `verify_node` using `EvidenceVerifier._classify` |
| `ai/langgraph/graphs/verification_graph.py` | Compiled sub-graph + `invoke_verification_graph()` |
| `tests/unit/test_verification_graph.py` | 2 unit tests for the verification graph |

---

## 2. Files Modified

| File | Change |
|------|--------|
| `ai/langgraph/graphs/chat_graph.py` | Replaced direct `citation_verification_node` with `_run_verification` wrapper calling sub-graph |
| `ai/langgraph/graphs/enrichment_graph.py` | Replaced direct `evidence_verification_node` with `_run_verification` wrapper calling sub-graph |
| `ai/langgraph/graphs/question_generation_graph.py` | Replaced direct `verify_evidence_node` with `_run_verification` wrapper calling sub-graph |
| `apps/ai_classroom/enrichment_nodes.py` | Added `content` to refs in `citation_stitch_node` for sub-graph compatibility |

---

## 3. Design Decision: `_classify` vs `verify`

The verification sub-graph uses `EvidenceVerifier._classify()` instead of `EvidenceVerifier.verify()`:

| Method | DB Access | Use Case |
|--------|-----------|----------|
| `verify(block_content, source_refs)` | Yes — queries `NoteChunk` by `chunk_id` | Original enrichment flow where refs have chunk IDs |
| `_classify(block_content, cited_contents)` | No — operates on already-resolved strings | Sub-graph where contents are passed directly |

This avoids unnecessary DB queries inside the graph and makes the sub-graph truly reusable.

---

## 4. Integration Points

### 4.1 Chat Graph

```python
def _run_verification(state: ChatState) -> dict:
    verification_state = VerificationState(
        content=state.get("answer", ""),
        cited_contents=state.get("cited_contents", []),
        ...
    )
    result = invoke_verification_graph(verification_state)
    return {
        "verification_status": result.get("verification_status", "not_verified"),
        "verification_score": result.get("verification_score", 0.0),
    }
```

### 4.2 Enrichment Graph

```python
def _run_verification(state: EnrichmentState) -> dict:
    for item in stitched:
        refs = item.get("refs", [])
        cited_contents = [ref.get("content", "") for ref in refs]
        verification_state = VerificationState(
            content=item.get("content", ""),
            cited_contents=cited_contents,
            ...
        )
        result = invoke_verification_graph(verification_state)
        verified.append({...})
```

### 4.3 Question Generation Graph

```python
def _run_verification(state: QuestionGenerationState) -> dict:
    for q in state.get("verified_questions", []):
        if not q.get("is_valid", False):
            verified.append({**q, "verification_status": "skipped"})
            continue
        verification_state = VerificationState(
            content=q.get("prompt", ""),
            cited_contents=[q.get("prompt", "")],
            ...
        )
        result = invoke_verification_graph(verification_state)
        verified.append({...})
```

---

## 5. LangSmith Traces

| Trace Name | Type | Purpose |
|------------|------|---------|
| `studyai.verification` | chain | Full verification sub-graph execution |
| `studyai.verification.evidence` | tool | Evidence verification node |

When invoked from parent graphs, these appear as nested runs under:
- `studyai.chat.classic`
- `studyai.enrichment`
- `studyai.question_generation`

---

## 6. Preserved Behaviors

- **Deterministic verification** — `EvidenceVerifier._classify` unchanged
- **Lexical overlap scoring** — same tokenization and thresholds
- **Verification statuses** — `supported`, `partially_supported`, `unsupported`, `not_verified`
- **Score rounding** — `round(score, 4)` preserved

---

## 7. Tests

### New Tests (2 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_verification_graph.py` | Graph build, graph invocation with mocked `_classify` |

### Existing Tests (51 pass)

| Test File | Coverage |
|-----------|----------|
| `tests/unit/test_chat_graph.py` | Chat graph nodes and integration |
| `tests/unit/test_enrichment_graph.py` | Enrichment graph nodes and integration |
| `tests/unit/test_question_generation_graph.py` | Question generation graph nodes and integration |
| `tests/api/test_ai_classroom.py` | End-to-end enrichment API tests |

---

## 8. Validation

- 53/53 total tests pass
- All existing enrichment API tests pass
- Verification sub-graph builds and executes correctly
- No DB access in verification sub-graph (uses `_classify`)

---

## 9. Next Steps

1. Proceed to **Phase 6: Adaptive Tests** migration
