# AI Evaluation — harness runnable, datasets still empty

Runners exist and are math-tested (Phase 6); Phase 7 adds nothing to the datasets themselves.

| Metric | Runner ready? | Dataset | Measured? |
|---|---|---|---|
| Retrieval Recall@k / MRR / P@k | ✅ `run_retrieval_cases` | ❌ none | Not currently measured |
| Citation support precision/recall | ✅ `run_citation_cases` vs rules-v1 | ❌ none | Not currently measured |
| Question quality (correctness/relevance/difficulty alignment) | ❌ no runner yet | ❌ none | Not currently measured |
| Chat answer correctness / citation correctness | ❌ no runner yet | ❌ none | Not currently measured |
| OCR CER/WER | ❌ | ❌ | Not currently measured (OCR mocked) |

Reference: [`../phase_1/ai/AI_EVALUATION.md`](../../phase_1/ai/AI_EVALUATION.md).

Phase 7 note: question generation and chat now produce artifacts an evaluation runner can target — authoring their case schemas is queued with real-model work.
