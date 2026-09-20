# Phase A Report: Candidate Generation Audit & Baseline Measurement

**Phase:** `candidate_generation_v2` (Phase A: Audit & Measure)  
**Evaluator:** Senior IR/ML Engineer  
**Date:** 2026-09-20  
**Status:** COMPLETE (Ready for checkpoint review before writing Phase B extractor code)  

---

## 1. Executive Summary

1. **Root Cause of Baseline Noise (82.9%):**  
   The baseline extractor [`extract_candidates_from_chunk`](file:///Users/yash/CV_Project/StudyAI/backend/apps/ai_classroom/gap_candidates.py#L107-L225) generates **1,191 candidates** across the 40 base cases. **1,186 of those 1,191 candidates (99.6%) come from the sliding n-gram fallback**. The n-gram generator yields **905 ungrounded noise phrases** (raw precision = 23.7%, unique-concept precision = **12.4%**).
2. **Gold Extractive Recall Ceiling:**  
   Across the 40 base cases (242 gold concepts), the **extractive ceiling is 77.3% lenient** (where the concept's topic or an alias appears verbatim in its reference chunk) and **39.3% strict** (topic only). The theoretical maximum recall achievable by any purely extractive Stage 1 model without generative paraphrasing is 77.3%.
   - `gap`: 84.2% ceiling (96/114)
   - `partial`: 88.9% ceiling (8/9)
   - `covered`: 51.5% ceiling (35/68)
   - `off_scope`: 94.1% ceiling (48/51)
3. **Dev / Test Split Established:**  
   20 dev cases ($n \pmod 4 \in \{1, 2\}$) and 20 test cases ($n \pmod 4 \in \{0, 3\}$) frozen in [`split.json`](file:///Users/yash/CV_Project/StudyAI/tests/evaluation/results/candidate_generation_v2/split.json). Baseline unique-concept precision is **12.2% on Dev** and **12.6% on Test**.
4. **Reference Chunk Structure:**  
   `golden_v2` corpus chunks contain **only `text`** (`base_id` and `subject` are evaluation fields stripped prior to extraction). No headings, sections, or chapter hierarchy exist in the dataset. Section-heading extraction paths are structurally unavailable on `golden_v2`.

---

## 2. A1. Audit of Baseline `gap_candidates.py`

The baseline extractor in [`backend/apps/ai_classroom/gap_candidates.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/ai_classroom/gap_candidates.py) implements the following extraction sequence:

1. **Domain Dictionary Matching (`DOMAIN_DICTIONARY`):**
   - Matches against a hardcoded set of ~60 strings in `DOMAIN_CONCEPTS` (e.g. `'time complexity'`, `'amortized analysis'`, `'chain rule'`, `'inertial frame'`).
   - Confidence: `0.95`.
   - Leakage Risk: High if concepts from golden sets are hardcoded; was hand-authored during `golden_v1`.
2. **Regex Technical Patterns (`TECHNICAL_PATTERN`):**
   - Evaluates 16 fixed regular expressions:
     - `\b(?:time|space|amortized|asymptotic|worst|best|average|computational)\s+(?:complexity|analysis)\b`
     - `\b(?:proof|correctness|termination|invariant|loop)\s+(?:of|for)?\s*\w*\b`
     - `\b(?:inertial|reference)\s+frames?\b`
     - `\b(?:vector|scalar|tensor)\s+(?:nature|quantity|field)\b`
     - `\b(?:net|individual|resultant|total)\s+force\b`, etc.
   - Confidence: `0.85`.
3. **Capitalized Proper Noun Phrases (`CAPITALIZED_PHRASE`):**
   - Matches multi-word capitalized sequences `[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}` containing domain keywords.
   - Confidence: `0.75`.
4. **Heading Extraction (`HEADING`):**
   - **NOT IMPLEMENTED** in baseline. No heading extraction exists in `gap_candidates.py`.
5. **N-Gram Sliding Window Fallback (`NGRAM`):**
   - Removes stopwords and short tokens ($\le 3$ characters), then generates all consecutive 2-grams and 3-grams.
   - Boosts confidence to `0.55` if keyword matches; otherwise `0.45`.
6. **Deduplication and Capping:**
   - Deduplicates case-insensitively using exact phrase strings.
   - Sorts by confidence descending and caps at `max_candidates` (default 5 or 8 per chunk).

---

## 3. A2. Baseline Source Breakdown (40 Base Cases, 242 Concepts)

Measured on the unmodified baseline extractor across all 40 base cases:

| Extraction Source | Candidates Generated | Total Hits | Raw Precision | Unique Concepts Recalled | Marginal Recall (Only This Source) | Fragments |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **`DOMAIN_DICTIONARY`** | 4 | 2 | 50.0% | 2 (0.8%) | **0 (0.0%)** |
| **`TECHNICAL_PATTERN`** | 1 | 0 | 0.0% | 0 (0.0%) | **0 (0.0%)** |
| **`CAPITALIZED_PHRASE`** | 0 | 0 | 0.0% | 0 (0.0%) | **0 (0.0%)** |
| **`NGRAM`** | **1,186** | 281 | 23.7% | **148 (61.2%)** | **146 (60.3%)** |
| **Total Pipeline** | **1,191** | **283** | **23.8%** | **148 (61.2%)** | — | **13** |

### Key Source Findings:
1. **Source of the 82.9% Noise:** `NGRAM` generates 1,186 out of 1,191 candidates (99.6% of volume) and **905 noise phrases**.
2. **Domain Dictionary Marginal Value:** The hardcoded `DOMAIN_CONCEPTS` dictionary provides **0.0% marginal recall**. All 2 concepts it hit were also captured by n-grams. It represents pure leakage risk from `golden_v1` with zero unique utility on `golden_v2`.
3. **Pattern Inefficacy:** `TECHNICAL_PATTERN` matched only 1 candidate in 40 cases, yielding 0 hits.
4. **Unique-Concept vs Raw Precision:** While raw hit rate is 23.8% (due to overlapping n-gram hits like `"binary search"` and `"binary search takes"` hitting the same concept), the **unique-concept precision is only 12.4%** (148 unique concepts / 1,191 candidates).

---

## 4. A3. Reference Structure Inspection

### A. `golden_v2` Corpus Chunks
Each chunk in `golden_v2.json["corpus"]` contains:
```json
{
  "text": "Each comparison halves the search range, so binary search takes O(log n)...",
  "subject": "Computer Science",
  "base_id": "g2_001"
}
```
- `subject` and `base_id` are evaluation labels and are stripped before extraction.
- **Finding:** There are **no headings, sections, page numbers, chapter titles, document hierarchy, or paragraph order metadata** in `golden_v2`.
- **Engineering Decision:** Section 4's heading extraction path is structurally unavailable on `golden_v2`. Extraction on `golden_v2` must rely strictly on chunk text content (definitional patterns, syntactic noun phrases, salience scoring). For production data where document headings exist, the heading path will be implemented as an optional ingestion-time enricher.

### B. Production `NoteChunk` Schema
From [`backend/apps/retrieval/models.py`](file:///Users/yash/CV_Project/StudyAI/backend/apps/retrieval/models.py#L51-L91):
- Fields: `id`, `document`, `profile`, `subject`, `revision_id`, `page_start`, `page_end`, `chunk_index`, `content`, `content_hash`, `source_type`, `reference_book`, `embedding`, `tsvector_content`, `stale`.
- Production chunks store page spans (`page_start`, `page_end`) and index ordering (`chunk_index`), but do not store explicit markdown headings or section headers.

---

## 5. A4. Frozen Match Function & Extractive Recall Ceiling

The frozen match specification is committed to [`tests/evaluation/results/candidate_generation_v2/match_spec.md`](file:///Users/yash/CV_Project/StudyAI/tests/evaluation/results/candidate_generation_v2/match_spec.md).

### Match Rules Summary
- **Normalization:** Lowercase, punctuation to space, safe plural stripping, whitespace collapsed.
- **Fragment Rule:** If a candidate is a proper sub-phrase or single token of a multi-word gold target, it is classified as `FRAGMENT` and **never a hit**.
- **Hit Rule:** Exact normalized match OR token-set containment where the candidate contains all content tokens of the gold target and adds at most 2 extra tokens.

### Extractive Recall Ceiling (40 Base Cases, 242 Concepts)

| Status | Total Concepts | Strict Ceiling (Topic in Chunk) | Lenient Ceiling (Topic or Alias in Chunk) |
|:---|:---:|:---:|:---:|
| **`gap`** | 114 | 33 (28.9%) | **96 (84.2%)** |
| **`partial`** | 9 | 3 (33.3%) | **8 (88.9%)** |
| **`covered`** | 68 | 18 (26.5%) | **35 (51.5%)** |
| **`off_scope`** | 51 | 41 (80.4%) | **48 (94.1%)** |
| **Overall** | **242** | **95 (39.3%)** | **187 (77.3%)** |

*Verification:* Confirms the reference figures cited in the prompt (76.4%-77.3% lenient ceiling; gap: 84.2%, partial: 88.9%, covered: 51.5%, off-scope: 94.1%).

---

## 6. A5. Baseline Metrics on Frozen Dev and Test Splits

Partitioned using the pre-registered rule:
- **Dev Split:** $n \pmod 4 \in \{1, 2\}$ (20 cases: `g2_001`, `g2_002`, `g2_005`, `g2_006`, `g2_009`, `g2_010`, `g2_013`, `g2_014`, `g2_017`, `g2_018`, `g2_021`, `g2_022`, `g2_025`, `g2_026`, `g2_029`, `g2_030`, `g2_033`, `g2_034`, `g2_037`, `g2_038`).
- **Test Split:** $n \pmod 4 \in \{0, 3\}$ (20 cases: `g2_003`, `g2_004`, `g2_007`, `g2_008`, `g2_011`, `g2_012`, `g2_015`, `g2_016`, `g2_019`, `g2_020`, `g2_023`, `g2_024`, `g2_027`, `g2_028`, `g2_031`, `g2_032`, `g2_035`, `g2_036`, `g2_039`, `g2_040`).

| Metric | Dev Split (20 Cases) | Test Split (20 Cases) | Total Baseline (40 Cases) | Pre-Registered Target (Test) |
|:---|:---:|:---:|:---:|:---:|
| **Candidates / Case** | **28.6** (572 total) | **30.9** (619 total) | 29.8 (1,191 total) | $\le 10$ candidates/case |
| **Total Hits** | 141 | 142 | 283 | — |
| **Raw Precision** | 24.7% | 22.9% | 23.8% | — |
| **Unique-Concept Precision** | **12.2%** (70 / 572) | **12.6%** (78 / 619) | **12.4%** (148 / 1,191) | $\ge 50.0\%$ |
| **Fragment Rate** | 0.70% (4 fragments) | 1.45% (9 fragments) | 1.09% (13 fragments) | $\le 2.0\%$ |
| **Gold Recall** | **59.8%** (70 / 117) | **62.4%** (78 / 125) | **61.2%** (148 / 242) | $\ge 0.85 \times \text{Ceil}$ & $\ge \text{Base}+0.15$ |
| **Extractive Lenient Ceiling** | 81.2% (95 / 117) | 73.6% (92 / 125) | 77.3% (187 / 242) | — |
| **Recall / Lenient Ceiling** | **73.7%** | **84.8%** | **79.1%** | $\ge 85.0\%$ |
| *Per-Status Recall:* | | | | |
| - `gap` Recall | 58.6% (34 / 58) | 66.1% (37 / 56) | 62.3% (71 / 114) | — |
| - `partial` Recall | 75.0% (3 / 4) | 80.0% (4 / 5) | 77.8% (7 / 9) | — |
| - `covered` Recall | 50.0% (16 / 32) | 41.7% (15 / 36) | 45.6% (31 / 68) | — |
| - `off_scope` Recall | 73.9% (17 / 23) | 78.6% (22 / 28) | 76.5% (39 / 51) | — |

---

## 7. Pre-Registered Phase C & D Targets (Section 8)

Frozen targets for the test split:
```text
C1  recall            >= 0.85 x extractive ceiling (lenient) [>= 62.6%] AND >= baseline + 0.15 [>= 77.4%]
C2  precision         >= 0.50 (unique-concept precision >= 50%)
C3  candidates/case   <= 10
C4  fragment rate     <= 2% of candidates
D1  end-to-end gap recall (arm C)              >= 0.70 and within 10 pts of ORACLE
D2  end-to-end gap precision, strict (arm C)   >= 0.60
D3  false-alarm rate, fully_covered + control  <= 10% of cases
```

---

## CHECKPOINT - Awaiting Review

Phase A audit, frozen match specification ([match_spec.md](file:///Users/yash/CV_Project/StudyAI/tests/evaluation/results/candidate_generation_v2/match_spec.md)), split definitions ([split.json](file:///Users/yash/CV_Project/StudyAI/tests/evaluation/results/candidate_generation_v2/split.json)), and baseline measurements are complete and verified.

Please review this Phase A report and provide confirmation to proceed to Phase B (Implementation of the Reference-Structured Extractor).
