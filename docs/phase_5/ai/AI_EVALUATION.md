# AI Evaluation

## Status: ❌ Nothing is measured (unchanged)

All metrics remain **not currently measured** — see [`../phase_1/ai/AI_EVALUATION.md`](../../phase_1/ai/AI_EVALUATION.md).

Phase 5 additions relevant to future evaluation:

- Retrieval is now exercisable, so Recall@k / MRR measurement becomes *possible* — the harness and labeled dataset still do not exist.
- Embedding quality caveat: with the hashing embedder, semantic metrics would measure lexical behavior only; meaningful evaluation should follow the neural-model swap (F-001) or be run explicitly to document hashing-grade numbers.
- RRF constants (k=60, depth 50) are untuned — flagged as calibration targets alongside citation thresholds.
