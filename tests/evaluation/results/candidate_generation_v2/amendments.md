# Amendment 1 - Phase A thresholds (dated before any Phase B artifact)

Reason: Phase A showed C1 (baseline + 0.15 = 77.4%) exceeds the test-split lenient ceiling
(73.6%, 92/125), C1's ratio clause was already met by the baseline (62.4% recall, 84.8% of
ceiling), C2 (0.50) required <= 7.8 candidates/case at the recall floor, and D1's ORACLE
comparison ignored the extractive ceiling. No Phase B or C output existed when this was written.

Changed: C1, C2, C3, C4 (guard only), D1, decision definitions, and the ORACLE-EXTRACTABLE arm.
Unchanged: D2, D3, match_spec.md, split.json, the extractor/leakage rules.

Definitions fixed here:
- Precision = unique gold concepts hit / candidates emitted after dedup (test split, strict).
- Candidates per chunk = emitted / chunks in the split; also report the max per chunk.
- Lenient precision counts only human-reviewed labels from unmatched_sample.csv.

Reference: Phase A artifacts at commit pending.

---

## Confirmed Thresholds

```text
C1  test recall (overall) >= 0.85 x lenient ceiling (>= 62.6%); AND gap recall >= baseline gap recall (66.1%)
C2  strict unique-concept precision >= 0.40 [add lenient (human-reviewed sample) >= 0.60]
C3  candidates <= 1.6 per chunk (~10 per case on test); report per-chunk budget used
C4  fragment rate <= 2% (regression guard; also report single-token candidate rate)
D1  end-to-end gap recall >= 0.70, and >= 0.85 x ORACLE-EXTRACTABLE gap recall
D2  end-to-end gap precision, strict (arm C) >= 0.60
D3  false-alarm rate, fully_covered + control <= 10% of cases
```

## Decisions

- **PASS:** C1–C4 and D1–D3 all met.
- **PARTIAL:** strict test precision improved by at least +0.15 absolute over baseline, but any other threshold is not met.
- **NO IMPROVEMENT:** precision gain is under +0.15.
- **BLOCKED:** leakage test fails, match spec was changed after tuning, dev/test disagree wildly, or labels cannot support the measurement.
