# Evaluation Rubrics for StudyAI Enrichment Pipeline

## Overview

These rubrics define the scoring criteria for each evaluation dimension. They are designed to be used by another engineer without needing clarification.

---

## 1. Retrieval Rubric

### Metric Definitions

| Metric | Definition | Target |
|--------|------------|--------|
| **Recall@K** | Fraction of cases where ≥1 expected chunk appears in top-K results | ≥ 0.70 |
| **Precision@K** | Average fraction of retrieved chunks that are expected | ≥ 0.30 |
| **MRR** | Mean reciprocal rank of first expected chunk | ≥ 0.50 |

### Failure Analysis Categories

For each failed retrieval (expected chunk not in top-K), classify as:

1. **Lexical Mismatch** - Query terms don't overlap with chunk content
2. **Embedding Mismatch** - Semantic similarity low despite related content
3. **Wrong Profile** - Retrieved chunks from different user profile
4. **Stale Chunk** - Retrieved chunk marked stale=true
5. **Missing in DB** - Expected chunk doesn't exist in database
6. **Ranked Too Low** - Expected chunk exists but ranked > K
7. **Distractor Dominance** - Unrelated chunks score higher

### Scoring

| Score | Recall@K | Precision@K | MRR |
|-------|----------|-------------|-----|
| 4 (Excellent) | ≥ 0.90 | ≥ 0.50 | ≥ 0.80 |
| 3 (Strong) | ≥ 0.70 | ≥ 0.30 | ≥ 0.50 |
| 2 (Acceptable) | ≥ 0.50 | ≥ 0.20 | ≥ 0.30 |
| 1 (Partial) | ≥ 0.30 | ≥ 0.10 | ≥ 0.15 |
| 0 (Failed) | < 0.30 | < 0.10 | < 0.15 |

---

## 2. Citation Rubric

### Validity (Does the chunk exist?)

| Score | Criteria |
|-------|----------|
| 4 | All cited chunks exist in database |
| 3 | 1-2 missing chunks out of >10 total |
| 2 | 3-5 missing chunks |
| 1 | 6-10 missing chunks |
| 0 | >10 missing chunks or no citations at all |

### Provenance (Correct document/revision?)

| Score | Criteria |
|-------|----------|
| 4 | All citations point to correct document and revision |
| 3 | 1-2 wrong document/revision citations |
| 2 | 3-5 wrong |
| 1 | 6-10 wrong |
| 0 | >10 wrong or systematic provenance failure |

### Support (Does chunk support claim?)

Based on `verification_status` from EvidenceVerifier:

| Score | Criteria |
|-------|----------|
| 4 | ≥ 80% of citations "supported", 0% "unsupported" |
| 3 | ≥ 60% "supported", ≤ 10% "unsupported" |
| 2 | ≥ 40% "supported", ≤ 20% "unsupported" |
| 1 | ≥ 20% "supported", ≤ 30% "unsupported" |
| 0 | < 20% "supported" or > 30% "unsupported" |

### Completeness (Are important claims cited?)

| Score | Criteria |
|-------|----------|
| 4 | All non-trivial claims have citations; no gap_fill blocks without refs |
| 3 | 1-2 uncited claims |
| 2 | 3-5 uncited claims |
| 1 | 6-10 uncited claims |
| 0 | Many uncited claims or gap_fill blocks without refs |

---

## 3. Gap Detection Rubric

### Precision (Of detected gaps, how many are real?)

| Score | Criteria |
|-------|----------|
| 4 | ≥ 90% precision (FP ≤ 10%) |
| 3 | ≥ 70% precision |
| 2 | ≥ 50% precision |
| 1 | ≥ 30% precision |
| 0 | < 30% precision |

### Recall (Of real gaps, how many detected?)

| Score | Criteria |
|-------|----------|
| 4 | ≥ 80% recall (FN ≤ 20%) |
| 3 | ≥ 60% recall |
| 2 | ≥ 40% recall |
| 1 | ≥ 20% recall |
| 0 | < 20% recall |

### Gap Description Quality

| Score | Criteria |
|-------|----------|
| 4 | All detected gaps have specific, actionable topics referencing correct reference chunks |
| 3 | Minor vagueness in 1-2 gap topics |
| 2 | Several vague or generic gap topics (e.g., "more detail needed") |
| 1 | Most gaps vague or incorrectly attributed |
| 0 | Gaps are nonsensical or completely unrelated |

### False Positive Types (record for analysis)

- **Invented Gap** - Topic not in reference material at all
- **Already Covered** - Topic actually covered in user note
- **Trivial Gap** - Missing info too minor to matter (e.g., missing a single synonym)
- **Wrong Reference** - Cites reference chunk that doesn't contain the topic

---

## 4. Gap Filling Rubric

Per detected gap, rate the generated fill block:

| Score | Label | Criteria |
|-------|-------|----------|
| 4 | **Correct Strong** | Fully addresses gap topic; well-grounded in cited reference; clear explanation; appropriate detail level; cites correct reference chunk |
| 3 | **Correct Shallow** | Addresses gap topic correctly but minimal detail (1 sentence); cites correct reference; no errors |
| 2 | **Partially Correct** | Addresses part of gap; contains minor inaccuracies or omissions; cites correct reference |
| 1 | **Incorrect** | Contradicts source note or reference; hallucinates facts; cites wrong chunk; doesn't address gap |
| 0 | **Missing** | No gap_fill block generated for this expected gap |

### Required Attributes (all must be true for score ≥ 2)

- [ ] **Addresses Gap** - Content directly covers the missing topic
- [ ] **Relevant to Note** - Connects back to user note context
- [ ] **No Contradiction** - Does not contradict source note or reference
- [ ] **Grounded** - Claims supported by cited reference chunk
- [ ] **Appropriate Attribution** - Cites the correct reference chunk

---

## 5. Question Rubric

Per generated question, rate on 6 dimensions (0-1 each):

| Dimension | 1.0 (Excellent) | 0.7 (Good) | 0.4 (Fair) | 0.1 (Poor) |
|-----------|-----------------|------------|------------|------------|
| **Relevance** | Tests core concept from note | Tests mentioned concept | Tests peripheral concept | Tests unrelated concept |
| **Connection** | Clearly tied to specific chunk | Tied to note generally | Weak connection | No clear connection |
| **Non-Trivial** | Requires reasoning/application | Requires understanding | Simple recall/definition | Trivial (e.g., "What is X?") |
| **Appropriate Difficulty** | Matches expected range | One level off | Two levels off | Wrong difficulty |
| **Answerable** | Correct answer clearly in source | Answer inferable | Answer ambiguous | Answer not in source |
| **Good Distractors** | Plausible, distinct, same format | Mostly plausible | Some obvious | Obviously wrong |

### Overall Score = Average of 6 dimensions

| Overall | Label |
|---------|-------|
| ≥ 0.85 | Excellent |
| ≥ 0.70 | Strong |
| ≥ 0.55 | Acceptable |
| ≥ 0.40 | Partial |
| < 0.40 | Poor |

### Aggregate Thresholds

| Metric | Target |
|--------|--------|
| Avg Overall | ≥ 0.70 |
| Duplicate Rate | ≤ 5% |
| Trivial Rate | ≤ 10% |
| Coverage | ≥ 80% of expected topics tested |

---

## 6. Tag Rubric

Per generated tag, rate on 5 dimensions (0-1 each):

| Dimension | 1.0 | 0.7 | 0.4 | 0.1 |
|-----------|-----|-----|-----|-----|
| **Relevance** | Core concept in note | Mentioned concept | Peripheral | Unrelated |
| **Coverage** | Covers unique expected concept | Covers expected concept | Partial coverage | No coverage |
| **Non-Redundant** | Unique stable_key | Similar to 1 other | Similar to 2+ | Near-duplicate |
| **Non-Generic** | Specific academic term | Moderately specific | Generic (chapter, example) | Very generic |
| **Supported** | Token appears in chunks | Token in reference | Token not found | N/A |

### Overall Score = Average of 5 dimensions

### Aggregate Thresholds

| Metric | Target |
|--------|--------|
| Avg Overall | ≥ 0.70 |
| Redundant Pairs | ≤ 1 per document |
| Generic Tags | 0 |
| Unsupported Tags | ≤ 1 per document |
| Recall (vs expected concepts) | ≥ 60% |

---

## 7. Overall Enrichment Rubric

Holistic rating per document (0-4):

| Score | Label | Criteria |
|-------|-------|----------|
| 4 | **Excellent** | Comprehensive, accurate, well-structured study resource; adds significant value beyond source; all gaps filled well; questions and tags high quality; would be genuinely useful for a student |
| 3 | **Strong** | Good coverage and accuracy; minor issues (shallow gap fill, 1-2 weak questions); clearly useful for studying |
| 2 | **Acceptable** | Baseline useful; covers main points; some gaps missed or poorly filled; questions/tags acceptable but not great; a student would get some value |
| 1 | **Partial** | Some value but significant issues (hallucinations, missed major gaps, poor questions, generic tags); not reliable as study aid |
| 0 | **Failed** | Incorrect/harmful; contradicts source; mostly hallucinated; no value for studying |

### Required for Score ≥ 2

- [ ] No factual contradictions with source
- [ ] At least 50% of expected gaps detected
- [ ] At least 50% of detected gaps filled correctly
- [ ] Citation support rate ≥ 40%
- [ ] At least 2 relevant questions generated
- [ ] At least 2 relevant, non-generic tags

---

## 8. Latency Targets (Informational)

| Stage | Target (ms) | Acceptable (ms) |
|-------|-------------|-----------------|
| Retrieval | ≤ 500 | ≤ 2000 |
| Draft | ≤ 10000 | ≤ 30000 |
| Gap Detection | ≤ 8000 | ≤ 20000 |
| Gap Filling | ≤ 10000 | ≤ 30000 |
| Citation Stitching | ≤ 500 | ≤ 1000 |
| Verification | ≤ 200 | ≤ 500 |
| **Total** | ≤ 30000 | ≤ 90000 |

---

## Usage Instructions

1. **For automated metrics** (retrieval, citation support, gap detection P/R/F1): Use the computed values directly against the thresholds above.

2. **For manual rubrics** (gap fill quality, question quality, tag quality, overall):
   - Have 2 engineers independently rate a sample of 20+ outputs
   - Compute inter-rater agreement (Cohen's kappa)
   - Resolve disagreements through discussion
   - Apply calibrated ratings to full dataset

3. **For baseline establishment**: Run on golden dataset v1, record all scores, document any rubric ambiguities for future refinement.

4. **For regression testing**: Compare new run aggregates against baseline. Flag any dimension dropping by ≥ 1 score level or ≥ 10% relative on automated metrics.