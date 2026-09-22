# Task: Structured candidate generation for StudyAI gap detection (Phase: candidate_generation_v2)

This phase decides whether better **deterministic Stage 1 candidate generation**, plus a fixed Qwen 2.5:7B 4-way classifier, is good enough to proceed to gap filling.

## 0. Verified starting state (do not re-litigate)

```text
Pipeline:  User note -> Reference retrieval -> Candidate generation -> Qwen classification -> Structured gaps
Stack:     ollama / qwen2.5:7b, sentence-transformers/all-MiniLM-L6-v2, 273 tests passing
Dataset:   golden_v2.json (+ golden_v2_metadata.json) is the sole ground truth
Prior eval (28 hand-picked gold candidates, 6 simple cases):
  Arch C (candidate -> Qwen 4-way):        accuracy 57.1%, MISSING F1 0.560, COVERED F1 0.909
  Arch D (embedding gate -> Qwen 3-way):   accuracy 17.9%   -> rejected, do NOT reuse the hard gate
Stage 1 baseline, 40 base cases:
  1,191 candidates, 204 "valid", 987 noise, precision 17.1%, gold recall 105/242 = 43.4%
  (204 valid hits cover only 105 concepts => ~2 hits per concept; baseline precision is NOT unique-concept precision)
Known Qwen issue: 5 of 9 gap misses were labelled PARTIALLY_COVERED while Qwen's own reason said the
concept was not mentioned. This confounds any downstream comparison (see Phase D).
```

Qwen must keep all four classes: MISSING, PARTIALLY_COVERED, COVERED, IRRELEVANT.
Do not recommend a larger LLM in this phase.

## 1. Non-negotiables (read first; violating any of these makes results invalid)

1. **No gold leakage.** The extractor may read only chunk text (and ordinary reference metadata that exists in the
   *production* schema). It must never read golden_v2 `concepts[]`, `topic`, `aliases`, `status`, `note_evidence`,
   `expected_*`, `must_not_flag`, `known_distractors`, `base_id`, `variant`, or `case_id`. In golden_v2 each corpus chunk
   has only `text`, `subject`, `base_id`; `base_id` and `subject` are evaluation fields and must be stripped before
   the extractor runs. No hardcoded dictionary entries may be derived from golden_v2 or golden_v1. Measure how many hits the
   *existing* domain dictionary contributes and report it as a leakage risk.
2. **One frozen match function** (Phase A4) decides what counts as a gold hit. It is written to
   `tests/evaluation/results/candidate_generation_v2/match_spec.md` and code before any extractor is tuned, and never
   changed afterwards.
3. **Dev/test split, frozen up front.** Split the 40 base cases by index n (g2_nnn): **dev = n mod 4 in {1,2}**,
   **test = n mod 4 in {0,3}** (20 cases each; every category and both control-variant parities are represented).
   Write the lists to `split.json` before any tuning. Tune only on dev. Run the test split once for the baseline and
   once for the final extractor. Report dev and test separately.
4. **Pre-registered thresholds** in Section 8 are fixed before running. Do not edit them after seeing results.
5. **Do not modify** (unless a concrete regression is found and documented): Qwen model, embedding model, retrieval
   ranking, RLS, reference-book filtering, citation verification, gap filling, question generation, tag generation.
   The only Qwen-side change permitted is the controlled prompt arm in Phase D.
6. **Stage 1 uses no Qwen.** It must be deterministic (same input -> same output) and cheap. MiniLM embeddings, spaCy /
   noun-chunk tooling, and statistical keyphrase scoring are allowed if already in (or trivially addable to) the
   dependencies; list what you used.
7. Use real Ollama qwen2.5:7b with fallback disabled, temperature 0, fixed seed, `num_ctx` recorded. Log raw outputs.
8. Commit `amendments.md` and the Phase A artifacts before writing extractor code, and record the hash.

## 2. Phase A - Audit and measure (no behavior changes)

- A1. Audit `backend/apps/ai_classroom/gap_candidates.py`.
- A2. Source breakdown on 40 base cases.
- A3. Reference structure inspection.
- A4. Frozen match function and recall ceiling.
- A5. Baseline on dev and test.

## 3. Phase B - Reference-structured extractor

Implement a new extractor with this priority order:
1. Headings/topics from real reference metadata, when present (confidence high).
2. Definitional patterns ("X is/are ...", "called/known as X", "X (ABBR)", parenthetical definitions).
3. Noun-phrase / keyphrase extraction with an operational validity test.
4. N-grams only as a low-confidence fallback, aggressively filtered.

Requirements:
- Preserve multi-word technical phrases.
- Normalization and deduplication.
- Author a must-merge / must-not-merge pair list before implementing.
- Canonical representation (`concept`, `canonical_key`, `source_chunk_id`, `source_type`, `confidence`, `extraction_method`).
- Off-scope handling: do not filter for relevance.
- No hard relevance gate anywhere.
- Do not import or reuse `DOMAIN_CONCEPTS` or the `TECHNICAL_PATTERN` regexes. Archive them, and add a test that the new extractor does not reference them.
- Expose `max_candidates_per_chunk`. Tune it on dev only, freeze the value, then apply it to test.

## 4. Phase C - Candidate-only evaluation

Input basis: each case's `reference_chunk_ids` on base cases. Tune on dev; run test once.
- Report candidates/case, unique-concept precision (strict: unmatched = noise), recall and recall/ceiling, F1, fragment rate.
- Recall separately for gap, partial, covered, off_scope concepts.
- Write `unmatched_sample.csv` (50 seeded random unmatched test candidates). Lenient precision uses only human-reviewed labels. If the sample is unreviewed, report C2-lenient as PENDING HUMAN REVIEW and suffix the decision with '(provisional)'.

## 5. Phase D - Downstream Qwen (test split, base variant)

Arms:
| Arm | Candidates | Qwen prompt |
|---|---|---|
| A | baseline extractor | current prompt |
| B | new extractor | current prompt |
| C | new extractor | grounded prompt |
| ORACLE-EXTRACTABLE | gold concepts whose topic or alias appears in the chunk | grounded prompt |
| ORACLE | all gold concept topics as candidates | grounded prompt |

Replace D1's ORACLE comparison with ORACLE-EXTRACTABLE.

## 6. Regression tests to add

- Quality, Normalization/dedup, Determinism, No leakage, Ground truth, Provenance, Isolation, Architecture.

## 7. Run order

1. Phase A (A1-A5) -> stop for review. (Completed)
2. Implement Phase B and its unit tests.
3. Phase C candidate-only (dev tuning, then test once).
4. Print Qwen call plan; Phase D arms on test base.
5. Noisy + control variants for best arm.
6. Final report.

## 8. Pre-registered thresholds (FROZEN by amendments.md)

All on the **test** split, strict matching, unique concepts:

```text
C1  test recall (overall) >= 0.85 x lenient ceiling (>= 62.6%); AND gap recall >= baseline gap recall (66.1%)
C2  strict unique-concept precision >= 0.40 [add lenient (human-reviewed sample) >= 0.60]
C3  candidates <= 1.6 per chunk (~10 per case on test); report per-chunk budget used
C4  fragment rate <= 2% (regression guard; also report single-token candidate rate)
D1  end-to-end gap recall >= 0.70, and >= 0.85 x ORACLE-EXTRACTABLE gap recall
D2  end-to-end gap precision, strict (arm C) >= 0.60
D3  false-alarm rate, fully_covered + control <= 10% of cases
```

## 9. Final decision (use exactly one, plus a readiness line)

- `PASS — candidate generation materially improved`: C1–C4 and D1–D3 all met.
- `PARTIAL — candidate generation improved but recall remains insufficient`: strict test precision improved by at least +0.15 absolute over baseline, but any other threshold is not met.
- `NO IMPROVEMENT — candidate generation remains the bottleneck`: precision gain is under +0.15.
- `BLOCKED — candidate-generation evaluation is not reliable`: leakage test fails, match spec was changed after tuning, dev/test disagree wildly, or labels cannot support the measurement.

Then one line: `GAP-FILLING READINESS: READY | NOT READY`.
