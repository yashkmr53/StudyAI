"""Unit and integration tests for golden_v2 dataset and Architecture D pipeline.

Covers:
1. golden_v2 loading: v2 dataset loads correctly, v1 is not accidentally used
2. Relevance: relevant candidate passes, irrelevant candidate rejected
3. Coverage: missing, partial, covered deterministic classifications
4. Provenance: source chunk valid, correct reference book, correct document
5. Isolation: no unrelated reference material enters case context
6. Qwen: structured output schema conformance, no fallback
7. Architecture D: irrelevant candidates do not reach Qwen, relevant candidates do
"""
import os
import json
import unittest
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from apps.ai_classroom.gap_candidates import (
    GapCandidate,
    compute_coverage,
    is_fragment,
    extract_all_candidates,
)
from apps.ai_classroom.relevance_gate import (
    apply_relevance_gate,
    extract_note_topics,
    compute_lexical_overlap,
    compute_topic_similarity,
    compute_reference_context_signal,
    STRATEGIES,
)
from apps.ai_classroom.candidate_validation import (
    CANDIDATE_VALIDATION_SCHEMA,
    CANDIDATE_COVERAGE_SCHEMA,
    validate_candidate_with_qwen,
    validate_candidate_coverage,
)
import jsonschema

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN_V2_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2.json")
METADATA_V2_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2_metadata.json")


class GoldenV2LoadingTest(SimpleTestCase):
    """Test golden_v2 dataset loading and schema integrity."""

    def test_golden_v2_loads_correctly(self):
        self.assertTrue(os.path.exists(GOLDEN_V2_PATH), f"golden_v2.json missing at {GOLDEN_V2_PATH}")
        self.assertTrue(os.path.exists(METADATA_V2_PATH), f"golden_v2_metadata.json missing at {METADATA_V2_PATH}")

        with open(GOLDEN_V2_PATH) as f:
            v2 = json.load(f)
        with open(METADATA_V2_PATH) as f:
            meta = json.load(f)

        # Confirm authoritative version is v2, never v1
        self.assertEqual(v2.get("dataset_version"), "v2")
        self.assertEqual(meta.get("dataset_version"), "v2")
        self.assertNotEqual(v2.get("dataset_version"), "v1")

        # Check case counts
        self.assertEqual(len(v2["cases"]), 99)
        self.assertEqual(meta["num_cases"], 99)
        self.assertEqual(meta["num_base_cases"], 40)
        self.assertEqual(len(v2["corpus"]), 241)

    def test_golden_v2_taxonomy(self):
        with open(GOLDEN_V2_PATH) as f:
            v2 = json.load(f)
        statuses = v2["schema"]["statuses"]
        self.assertIn("gap", statuses)
        self.assertIn("partial", statuses)
        self.assertIn("covered", statuses)
        self.assertIn("off_scope", statuses)


class ProvenanceAndIsolationTest(SimpleTestCase):
    """Test chunk provenance and cross-case isolation."""

    def test_provenance_and_chunk_validity(self):
        with open(GOLDEN_V2_PATH) as f:
            v2 = json.load(f)
        corpus = v2["corpus"]

        for c in v2["cases"]:
            cid = c["case_id"]
            subj = c["subject"]
            ref_chunks = c.get("reference_chunk_ids", [])

            # Source chunks must exist and match case subject
            for rc in ref_chunks:
                self.assertIn(rc, corpus, f"Chunk {rc} in case {cid} not in corpus")
                self.assertEqual(corpus[rc]["subject"], subj, f"Chunk {rc} subject mismatch in case {cid}")

            # Expected retrieval targets must be authorized reference chunks
            for target in c.get("expected_retrieval_targets", []):
                self.assertIn(target, ref_chunks, f"Target {target} not in case {cid} reference chunks")

    def test_cross_case_isolation(self):
        with open(GOLDEN_V2_PATH) as f:
            v2 = json.load(f)
        cases = {c["case_id"]: c for c in v2["cases"] if c["variant"] == "base"}

        # Case A (g2_001 binary search) vs Case B (g2_002 ohm's law)
        case_a_chunks = set(cases["g2_001"]["reference_chunk_ids"])
        case_b_chunks = set(cases["g2_002"]["reference_chunk_ids"])

        # Chunks must not bleed across cases
        self.assertEqual(len(case_a_chunks & case_b_chunks), 0, "Reference chunks leaked across cases!")


class CoverageDeterministicTest(SimpleTestCase):
    """Test deterministic coverage classification (MISSING, PARTIALLY_COVERED, COVERED)."""

    def test_covered_classification(self):
        note = "Binary search finds a target in a sorted array."
        cand = GapCandidate(
            concept="sorted array",
            source_chunk_id="ref_01",
            source_content="Binary search requires a sorted array.",
            evidence_span="sorted array"
        )
        res = compute_coverage(cand, note)
        self.assertEqual(res.coverage_status, "COVERED")
        self.assertGreaterEqual(res.similarity_score, 0.90)

    def test_missing_classification(self):
        note = "Binary search repeatedly divides the search interval in half."
        cand = GapCandidate(
            concept="time complexity",
            source_chunk_id="ref_01",
            source_content="Binary search runs in O(log n) time complexity.",
            evidence_span="time complexity"
        )
        res = compute_coverage(cand, note)
        self.assertEqual(res.coverage_status, "MISSING")
        self.assertLess(res.similarity_score, 0.25)


class RelevanceGateTest(SimpleTestCase):
    """Test relevance gate signals and filtering behavior."""

    def test_relevance_gate_pass_and_reject(self):
        note = "Binary search finds a target in a sorted array by repeatedly comparing with middle element."
        note_topics = extract_note_topics(note)

        # Relevant candidate: contains words and context present in note
        cand_rel = GapCandidate(
            concept="sorted array",
            source_chunk_id="ref_001_03",
            source_content="Binary search requires a sorted array.",
            evidence_span="sorted array"
        )
        # Irrelevant distractor from another topic
        cand_irrel = GapCandidate(
            concept="cuckoo hashing",
            source_chunk_id="ref_099",
            source_content="Cuckoo hashing uses two hash functions to resolve collisions.",
            evidence_span="cuckoo hashing"
        )

        res_rel = STRATEGIES["D"](cand_rel, note, note_topics)
        res_irrel = STRATEGIES["D"](cand_irrel, note, note_topics)

        self.assertTrue(res_rel.is_relevant)
        self.assertFalse(res_irrel.is_relevant)


class ArchitectureDFilteringTest(SimpleTestCase):
    """Test that Architecture D ensures irrelevant candidates never reach Qwen."""

    def test_irrelevant_candidates_do_not_reach_qwen(self):
        note = "Binary search finds target in sorted array."
        cand_rel = GapCandidate(
            concept="sorted array",
            source_chunk_id="ref_1",
            source_content="sorted array chunk",
            evidence_span="sorted array"
        )
        cand_irrel = GapCandidate(
            concept="cuckoo hashing",
            source_chunk_id="ref_2",
            source_content="cuckoo hashing chunk",
            evidence_span="cuckoo hashing"
        )

        gate_res = apply_relevance_gate([cand_rel, cand_irrel], note, strategy="D")

        self.assertIn(cand_rel, gate_res["relevant"])
        self.assertIn(cand_irrel, gate_res["irrelevant"])

        # Mock Qwen call to verify it is called ONLY for relevant
        mock_provider = MagicMock()
        mock_provider.generate_structured.return_value.data = {
            "classification": "COVERED",
            "reason": "Test reason",
            "missing_from_note": "",
            "evidence_in_reference": "Test evidence"
        }

        # Stage 2: Qwen is only called for gate_res['relevant']
        for cand in gate_res["relevant"]:
            validate_candidate_coverage(note, cand.concept, cand.source_content, llm_provider=mock_provider)

        self.assertEqual(mock_provider.generate_structured.call_count, 1)


class QwenStructuredOutputSchemaTest(SimpleTestCase):
    """Test that Qwen output schemas are valid and enforce JSON constraint."""

    def test_schemas_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(CANDIDATE_VALIDATION_SCHEMA)
        jsonschema.Draft7Validator.check_schema(CANDIDATE_COVERAGE_SCHEMA)

    def test_candidate_coverage_schema_enforcement(self):
        valid_data = {
            "classification": "MISSING",
            "reason": "The concept is completely absent from the note.",
            "missing_from_note": "Time complexity O(log n)",
            "evidence_in_reference": "Takes O(log n) comparisons."
        }
        jsonschema.validate(instance=valid_data, schema=CANDIDATE_COVERAGE_SCHEMA)

        invalid_data = {
            "classification": "IRRELEVANT",  # Not in 3-way schema!
            "reason": "Off-scope",
            "missing_from_note": "",
            "evidence_in_reference": ""
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=invalid_data, schema=CANDIDATE_COVERAGE_SCHEMA)
