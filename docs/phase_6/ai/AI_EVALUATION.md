# AI Evaluation — harness implemented, datasets empty

## What exists now (new in Phase 6)

- **EvalRun model** (`apps/evaluation/models.py`): kind (retrieval/citation), dataset_name, case_count, metrics JSON.
- **Retrieval runner**: computes Recall@k, MRR, Precision@k from cases `{query, expected_chunk_ids}` against the real `RetrievalService.search`.
- **Citation runner**: computes support precision/recall from cases `{block_content, cited_chunk_contents, expected_status}` against the real rules-v1 verifier verdicts.
- **Command**: `manage.py run_ai_evaluation --file <dataset.json> [--user email] [--k n]`.

Both runners are covered by fixture tests asserting the metric math (precision/recall = 1.0 on a crafted two-case dataset; recall_at_k = 1.0 on an indexed corpus).

## Metric status table

| Metric | Current measurement | Target | Dataset | Method | Status |
|---|---|---|---|---|---|
| Retrieval Recall@k | Not currently measured | TBD | none | labeled chunk ids per query | ❌ data; ✅ runner |
| MRR / Precision@k | Not currently measured | TBD | none | same | ❌ |
| Citation support precision/recall | Not currently measured | TBD after calibration | none | verifier verdict vs human label | ❌ data; ✅ runner math |
| Grounding accuracy / hallucination rate | Not currently measured | — | — | — | ❌ |
| OCR CER/WER/calibration | Not currently measured | — | — | — | ❌ (and OCR itself is mocked) |
| Tagging precision/recall | Not currently measured | — | — | — | ❌ (no tags yet) |

## Honest constraints

1. With 🔧 mock LLM and 🟡 hashing embeddings, measured numbers would describe synthetic behavior — meaningful evaluation starts at the real-model swaps.
2. Verifier thresholds (0.60/0.30) are uncalibrated placeholders; calibration requires the §26 labeled validation set.
3. No golden dataset (~30–50 notes + labeled claims) has been authored.
