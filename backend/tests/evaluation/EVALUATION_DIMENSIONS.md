# Evaluation Dimensions for StudyAI Enrichment Pipeline

## Overview

This document defines the evaluation dimensions for the StudyAI enrichment pipeline, based on the actual current implementation. Each dimension maps to a specific pipeline stage and measurable output.

---

## 1. Retrieval Evaluation

**Pipeline Stage**: `retrieve_chunks_node` → `RetrievalService.search`

**What is evaluated**: Whether the system retrieves the right source chunks for a given document.

**Input**: Document content (user note chunks) → query for reference chunks

**Output**: Top-K `NoteChunk` objects (both user and reference)

**Metrics**:
- **Recall@K**: Fraction of cases where at least one expected chunk appears in Top-K
- **Precision@K**: Fraction of returned chunks that are relevant
- **MRR (Mean Reciprocal Rank)**: Average of 1/rank of first relevant chunk

**Ground Truth Required**: For each evaluation case, a list of `expected_chunk_ids` that should be retrieved.

**Failure Analysis**: For each failed case, record:
- Query used (document content)
- Expected chunk ID
- Actual ranking of expected chunk (or "not retrieved")
- Retrieval score
- Reason for failure (lexical mismatch, embedding mismatch, wrong profile, stale chunk, etc.)

---

## 2. Drafting Evaluation

**Pipeline Stage**: `draft_node` (enrichment_draft prompt)

**What is evaluated**: Whether the generated explanation blocks remain consistent with the source note.

**Input**: `evidence_payload` (user_chunks + reference_chunks)

**Output**: `draft_result.blocks` - array of blocks with:
- `block_type`, `title`, `content`, `generation_method`, `source_chunk_ids`

**Criteria**:
- **Factual consistency**: Generated content does not contradict source chunks
- **Grounding**: Every claim in content is supported by cited chunks
- **Coverage**: Important concepts from source note are represented
- **Non-hallucination**: No claims unsupported by evidence

**Measurement**: Manual labeling + citation verification scores

---

## 3. Gap Detection Evaluation

**Pipeline Stage**: `gap_detection_node` (gap_detection prompt)

**What is evaluated**: Whether the system identifies genuine missing information rather than inventing gaps.

**Input**: `evidence_payload` (user_chunks + reference_chunks)

**Output**: `gaps_result.gaps` - array of gap objects:
- `topic`: String describing missing topic
- `reference_chunk_id`: UUID of reference chunk containing the missing info

**Ground Truth Required**: For each evaluation case, a list of `expected_gaps` (topic + reference_chunk_id)

**Metrics**:
- **Gap Detection Precision**: TP / (TP + FP) - Of detected gaps, how many are real
- **Gap Detection Recall**: TP / (TP + FN) - Of real gaps, how many detected

**Definitions**:
- **True Positive (TP)**: Detected gap matches an expected gap (same topic, same reference chunk)
- **False Positive (FP)**: Detected gap not in expected gaps (invented/unrelated)
- **False Negative (FN)**: Expected gap not detected

**Failure Analysis**: For each FP/FN, record the gap topic, reference chunk, and reason.

---

## 4. Gap Filling Evaluation

**Pipeline Stage**: `gap_fill_node` (gap_filling prompt)

**What is evaluated**: Whether generated gap-fill blocks address the identified gaps correctly.

**Input**: `evidence_payload` + `gaps_result.gaps`

**Output**: `fill_result.blocks` - array of blocks with `block_type="gap_fill"`

**Criteria** (per gap):
1. **Directly addresses gap**: Content covers the missing topic
2. **Relevant to original note**: Connects back to user note context
3. **No contradiction**: Does not contradict source note or reference
4. **No unsupported claims**: Claims are grounded in cited reference chunk
5. **Appropriate attribution**: Cites the correct reference chunk

**Quality Levels**:
- `correct_strong` - Fully addresses gap, well-grounded, clear
- `correct_shallow` - Addresses gap but minimal detail, thin grounding
- `partially_correct` - Some correct info but missing key aspects or minor errors
- `incorrect` - Contradicts source, hallucinates, or addresses wrong topic

**Measurement**: Manual labeling against rubric

---

## 5. Citation Evaluation

**Pipeline Stage**: `citation_stitch_node` + `evidence_verification_node`

**What is evaluated**: Whether every citation correctly points to supporting source material.

**Trace**: enrichment block → citation/source_ref → NoteChunk → revision → document

**Criteria**:
1. **Validity**: Referenced chunk exists in database
2. **Provenance**: Chunk belongs to correct document/revision
3. **Support**: Cited chunk content actually supports the generated claim (lexical overlap ≥ threshold)
4. **Completeness**: Important claims have citations; no uncited external claims

**Metrics**:
- **Citation Validity Rate**: % of citations pointing to existing chunks
- **Citation Provenance Rate**: % of citations pointing to correct document/revision
- **Citation Support Rate**: % of citations with verification_status = "supported"
- **Unsupported Claim Rate**: % of blocks with verification_status = "unsupported"

**Failure Analysis**: For each failed citation, record:
- Block content
- Cited chunk ID
- Verification status/score
- Reason (chunk missing, wrong revision, insufficient overlap, etc.)

---

## 6. Evidence Verification Evaluation

**Pipeline Stage**: `evidence_verification_node` (EvidenceVerifier)

**What is evaluated**: Whether the verification layer correctly distinguishes supported vs unsupported material.

**Note**: The verifier is deterministic rule-based (lexical overlap), not LLM-based.

**Test Cases**: Hand-labeled (block_content, cited_chunk_contents, expected_status)

**Metrics**:
- **Support Precision**: Of predicted "supported", how many truly supported
- **Support Recall**: Of truly supported, how many predicted "supported"
- **Per-class accuracy**: Supported / Partially Supported / Unsupported / Not Verified

---

## 7. Question Evaluation

**Pipeline Stage**: Question generation graph (`generate_questions_node` → `validate` → `verify` → `persist`)

**What is evaluated**: Quality of generated MCQs for studying.

**Input**: Document chunks (first N chunks)

**Output**: `Question` objects with prompt, options, answer_index, difficulty

**Criteria**:
- **Relevance**: Question tests knowledge from the source chunk
- **Connection**: Clearly tied to note content (not generic)
- **Coverage**: Important concepts across document are tested
- **Non-trivial**: Not definition-only or overly simple
- **Non-duplicate**: Unique questions per chunk
- **Appropriate difficulty**: Matches difficulty label
- **Answerable**: Correct answer is in source chunk
- **Distractor quality**: Wrong options are plausible but clearly wrong

**Ground Truth**: Manual labels for each generated question:
- `relevant` (0-1)
- `connected` (0-1)
- `non_trivial` (0-1)
- `appropriate_difficulty` (0-1)
- `answerable` (0-1)
- `good_distractors` (0-1)

**Aggregate**: Average across questions per document, then across documents.

---

## 8. Tag / Concept Evaluation

**Pipeline Stage**: `TaggingService.extract_for_document`

**What is evaluated**: Quality of extracted concept tags.

**Input**: Document chunks (all non-stale)

**Output**: `Tag` objects linked via `DocumentTag`

**Extraction Method**: Rule-based (top 5 frequent significant tokens ≥5 chars, not stopwords)

**Criteria**:
- **Relevance**: Tag represents a real concept in the document
- **Coverage**: Major concepts are captured
- **Non-redundancy**: No near-duplicate tags (e.g., "algorithm" + "algorithms")
- **Non-generic**: Not useless tags like "chapter", "section", "example"
- **Supported**: Tag token appears in source chunks
- **Consistency**: Same document → same tags across runs (deterministic)

**Metrics** (where expected concept list exists):
- **Tag Precision**: Of generated tags, how many in expected
- **Tag Recall**: Of expected tags, how many generated

**Without ground truth**: Manual audit of generated tags per document.

---

## 9. Overall Enrichment Quality

**Pipeline Stage**: Full pipeline (all stages)

**What is evaluated**: Does the final enriched note provide meaningful value beyond restating the original note?

**Criteria** (holistic, per document):
1. **Added value**: New explanations, connections, gap fills not in original
2. **Coherence**: Blocks flow logically, form a useful study resource
3. **Accuracy**: No factual errors vs source
4. **Completeness**: Covers key topics from source + reference
5. **Usability**: Would a student find this helpful for studying?

**Rating Scale** (0-4):
- `0` - Incorrect/harmful (hallucinations, contradictions)
- `1` - Partially useful (some value but significant issues)
- `2` - Acceptable (baseline useful, minor issues)
- `3` - Strong (clear value, well-structured, accurate)
- `4` - Excellent (exceptional study resource, comprehensive)

**Measurement**: Manual holistic rating with written justification.

---

## 10. Latency Measurement

**Pipeline Stage**: Each node

**What is measured**: Wall-clock time per stage

**Stages to time**:
- `chunking` (pre-pipeline, during ingestion)
- `embedding` (pre-pipeline, during ingestion)
- `retrieval` (retrieve_chunks_node)
- `draft` (draft_node)
- `gap_detection` (gap_detection_node)
- `gap_filling` (gap_fill_node, if triggered)
- `citation_stitching` (citation_stitch_node)
- `verification` (evidence_verification_node)
- `total_enrichment` (end-to-end)

**Method**: `time.monotonic()` at each node entry/exit (already logged via tracing)

**Report**: Mean, median, p95 per stage across evaluation runs.

---

## 11. Repeatability / Stability

**What is measured**: Variance across repeated runs on same input

**Dimensions**:
- Retrieval determinism (same chunks returned?)
- Enrichment output variance (block content, gaps, questions)
- Verification score stability
- Tag consistency
- Question consistency

**Method**: Run full pipeline N=3 times on each golden case; compute pairwise similarity.

---

## Evaluation Dataset Requirements

Each evaluation case must provide:

```json
{
  "case_id": "eval_001",
  "category": "simple_factual | multi_concept | implicit_relationship | missing_info | ambiguous | long_multi_chunk | multi_topic | distractor_prone",
  "input_note": "Full text of the user note",
  "subject": "Subject name",
  "expected_key_concepts": ["concept1", "concept2", ...],
  "expected_relevant_facts": ["fact1", "fact2", ...],
  "expected_retrieval_targets": ["chunk_id1", "chunk_id2", ...],
  "expected_gaps": [{"topic": "...", "reference_chunk_id": "..."}],
  "expected_citation_sources": ["chunk_id1", "chunk_id2", ...],
  "expected_question_characteristics": {
    "min_questions": 2,
    "topics": ["topic1", "topic2"],
    "difficulty_range": ["easy", "medium"]
  },
  "known_distractors": ["unrelated_fact1", "unrelated_fact2"],
  "reference_book_content": "Content of reference books available for retrieval"
}
```

---

## Evaluation Harness Architecture

```
tests/evaluation/
├── datasets/
│   ├── golden_v1.json          # Golden dataset (versioned)
│   └── golden_v1_metadata.json # Dataset metadata
├── rubrics/
│   ├── retrieval_rubric.md
│   ├── citation_rubric.md
│   ├── gap_detection_rubric.md
│   ├── gap_filling_rubric.md
│   ├── question_rubric.md
│   ├── tag_rubric.md
│   └── overall_rubric.md
├── runner/
│   ├── __init__.py
│   ├── enrichment_runner.py    # Runs full pipeline on dataset
│   ├── retrieval_eval.py       # Retrieval metrics
│   ├── citation_eval.py        # Citation metrics
│   ├── gap_eval.py             # Gap detection/fill metrics
│   ├── question_eval.py        # Question quality metrics
│   ├── tag_eval.py             # Tag quality metrics
│   └── latency_eval.py         # Stage timing
├── results/
│   ├── baseline.json           # Machine-readable results
│   └── baseline.md             # Human-readable report
└── evaluate.py                 # Main entry point
```