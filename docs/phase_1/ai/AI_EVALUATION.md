# AI Evaluation

## Status: ❌ No AI capability exists to evaluate; no metrics are measured

There is no evaluation harness, dataset, or metric computation in the repository. This page records the measurement plan and marks every metric's current state honestly.

## Metric inventory

### OCR

| Metric | Current measurement | Target | Dataset | Method | Status |
|---|---|---|---|---|---|
| CER | Not currently measured | TBD on golden set | none | diff canonical vs labeled transcription | ❌ |
| WER | Not currently measured | TBD | none | same | ❌ |
| Confidence calibration | Not currently measured | TBD | none | reliability curves | ❌ |

### Retrieval

| Metric | Current measurement | Target | Dataset | Method | Status |
|---|---|---|---|---|---|
| Recall@k | Not currently measured | TBD | none | labeled relevant chunks per query | ❌ |
| Precision@k | Not currently measured | TBD | none | same | ❌ |
| MRR | Not currently measured | TBD | none | same | ❌ |

### Grounding / citations

| Metric | Current measurement | Target | Dataset | Method | Status |
|---|---|---|---|---|---|
| Citation precision (support precision) | Not currently measured | TBD | human-labeled claims+evidence | verifier output vs labels | ❌ |
| Citation recall (support recall) | Not currently measured | TBD | same | same | ❌ |
| False-citation rate | Not currently measured | TBD | same | same | ❌ |
| Grounding accuracy | Not currently measured | TBD | enrichment cases | rubric review | ❌ |

### Generation

| Metric | Current measurement | Target | Dataset | Method | Status |
|---|---|---|---|---|---|
| Hallucination rate | Not currently measured | TBD | enrichment/chat cases | rubric review | ❌ |
| Answer correctness | Not currently measured | TBD | chat cases | rubric/labeled | ❌ |
| Question quality (correctness, relevance, difficulty alignment) | Not currently measured | TBD | question cases | review + attempt data | ❌ |
| Tagging precision/recall | Not currently measured | TBD | tagging cases | labeled tag sets | ❌ |

## Framework design commitments (spec §26)

- Versioned evaluation dataset **separate from production data**; sections: OCR, retrieval, enrichment, citation, tagging, question-generation, chat cases.
- Golden set ≈ 30–50 representative notes **plus** labeled queries/claims/questions.
- Citation ground truth is **independently human-labeled** (`claim`, `expected evidence`, `support status`). The verifier is never evaluated by inspecting its own score distribution.
- `EvalRun` records tie runs to dataset/prompt/model versions for regression gating in Phase 8.

No numbers appear anywhere in this file because none exist. Any future results must cite the dataset version and run ID.
