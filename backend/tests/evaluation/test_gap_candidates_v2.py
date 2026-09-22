"""Regression test suite for reference-structured extractor v2 (Phase B).

Verifies the 8 mandatory dimensions specified in Section 6:
1. Quality
2. Normalization / Deduplication (must-merge / must-not-merge pairs)
3. Determinism
4. No Leakage
5. Ground Truth validity
6. Provenance
7. Isolation
8. Architecture Isolation (no DOMAIN_CONCEPTS / TECHNICAL_PATTERN imports)
"""
import os
import json
import ast
import pytest
from apps.ai_classroom.gap_candidates_v2 import (
    GapCandidateV2,
    extract_candidates_from_chunk_v2,
    extract_all_candidates_v2,
    normalize_canonical_key,
    sanitize_reference_chunk,
    DISALLOWED_ENDINGS,
    SINGLE_TOKEN_NOISE,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2.json")
METADATA_PATH = os.path.join(BASE_DIR, "tests/evaluation/datasets/golden_v2_metadata.json")
PAIRS_PATH = os.path.join(BASE_DIR, "tests/evaluation/results/candidate_generation_v2/normalization_pairs.json")


# 1. QUALITY
def test_quality_constraints():
    """Verify that extracted candidates satisfy strict structural quality rules."""
    sample_text = (
        "Each comparison halves the search range, so binary search takes O(log n) "
        "comparisons in the worst case. The time complexity is logarithmic."
    )
    candidates = extract_candidates_from_chunk_v2("chunk_01", sample_text, max_candidates=5)
    
    assert len(candidates) > 0
    seen_keys = set()
    for cand in candidates:
        concept = cand.concept
        words = concept.split()
        
        # Rule 1: No candidate ends in a preposition or auxiliary
        last_word = words[-1].lower()
        assert last_word not in DISALLOWED_ENDINGS, f"Candidate '{concept}' ends in disallowed word: '{last_word}'"
        
        # Rule 2: No single-token candidate matches noise list
        if len(words) == 1:
            assert last_word not in SINGLE_TOKEN_NOISE, f"Single token candidate in noise list: '{concept}'"
            
        # Rule 3: No duplicate concepts under different surface forms
        key = cand.canonical_key
        assert key not in seen_keys, f"Duplicate key '{key}' in candidate list"
        seen_keys.add(key)


# 2. NORMALIZATION / DEDUP (MUST-MERGE / MUST-NOT-MERGE)
def test_normalization_and_deduplication():
    """Verify all 10 must-merge pairs merge and all 10 must-not-merge pairs remain distinct."""
    assert os.path.exists(PAIRS_PATH), f"Normalization pairs file not found: {PAIRS_PATH}"
    with open(PAIRS_PATH) as f:
        data = json.load(f)

    # Must merge
    for pair in data["must_merge_pairs"]:
        key_a = normalize_canonical_key(pair["term_a"])
        key_b = normalize_canonical_key(pair["term_b"])
        assert key_a == key_b, (
            f"Must-merge failed for '{pair['term_a']}' ({key_a}) and '{pair['term_b']}' ({key_b}): "
            f"{pair['rationale']}"
        )

    # Must NOT merge
    for pair in data["must_not_merge_pairs"]:
        key_a = normalize_canonical_key(pair["term_a"])
        key_b = normalize_canonical_key(pair["term_b"])
        assert key_a != key_b, (
            f"Must-not-merge failed (falsely merged) for '{pair['term_a']}' and '{pair['term_b']}' "
            f"-> both mapped to '{key_a}': {pair['rationale']}"
        )


# 3. DETERMINISM
def test_determinism():
    """Verify that running extraction twice on identical inputs yields byte-identical candidate lists in the same order."""
    text = (
        "Flow control prevents a fast sender from overwhelming a slow receiver. "
        "The receiver advertises a window size, and the sender limits unacknowledged data."
    )
    cands_run1 = extract_candidates_from_chunk_v2("chk_test", text, max_candidates=3)
    cands_run2 = extract_candidates_from_chunk_v2("chk_test", text, max_candidates=3)

    assert len(cands_run1) == len(cands_run2)
    for c1, c2 in zip(cands_run1, cands_run2):
        assert c1.concept == c2.concept
        assert c1.canonical_key == c2.canonical_key
        assert c1.confidence == c2.confidence
        assert c1.extraction_method == c2.extraction_method
        assert c1.salience_score == c2.salience_score
        assert c1.semantic_similarity == c2.semantic_similarity


# 4. NO LEAKAGE
def test_no_leakage():
    """Verify that the extractor rejects or strips injected evaluation fields."""
    leaked_chunk = {
        "chunk_id": "ref_999",
        "text": "Ohmic materials have a linear I-V curve.",
        "base_id": "g2_002",
        "case_id": "g2_002",
        "concepts": [{"topic": "Ohmic materials", "status": "gap"}],
        "status": "gap",
        "expected_gaps": ["Ohmic materials"],
    }
    
    # In strict mode: raises ValueError
    with pytest.raises(ValueError) as excinfo:
        sanitize_reference_chunk(leaked_chunk, strict_leakage_check=True)
    assert "Gold evaluation leakage error" in str(excinfo.value)

    # In standard mode: strips all forbidden fields cleanly
    sanitized = sanitize_reference_chunk(leaked_chunk, strict_leakage_check=False)
    for forbidden in ["base_id", "case_id", "concepts", "status", "expected_gaps"]:
        assert forbidden not in sanitized

    # Verify extract_all_candidates_v2 handles chunks cleanly without leaking
    cands = extract_all_candidates_v2([leaked_chunk], strict_leakage_check=False)
    assert len(cands) > 0
    for c in cands:
        assert "concepts" not in c.metadata
        assert "base_id" not in c.metadata


# 5. GROUND TRUTH VALIDITY
def test_ground_truth_validity():
    """Verify golden_v2.json and golden_v2_metadata.json integrity."""
    with open(DATASET_PATH) as f:
        v2 = json.load(f)
    with open(METADATA_PATH) as f:
        meta = json.load(f)

    assert meta["num_cases"] == len(v2["cases"])
    allowed_statuses = {"gap", "partial", "covered", "off_scope"}

    for case in v2["cases"]:
        assert "base_id" in case
        assert "case_id" in case
        assert "subject" in case
        assert "input_note" in case
        assert "reference_chunk_ids" in case
        assert "concepts" in case
        assert len(case["concepts"]) > 0

        for cp in case["concepts"]:
            assert "topic" in cp
            assert "status" in cp
            assert cp["status"] in allowed_statuses, f"Invalid status {cp['status']} in {case['case_id']}"


# 6. PROVENANCE
def test_provenance():
    """Verify every emitted candidate has a non-empty source_chunk_id and source_type == 'reference'."""
    chunks = [
        {"chunk_id": "chk_prov_1", "text": "Third normal form removes transitive dependencies."},
        {"chunk_id": "chk_prov_2", "text": "Denormalization reintroduces redundancy for query speed."}
    ]
    cands = extract_all_candidates_v2(chunks, max_per_chunk=2)
    assert len(cands) > 0
    for c in cands:
        assert c.source_chunk_id in {"chk_prov_1", "chk_prov_2"}
        assert c.source_type == "reference"
        assert c.extraction_method in {
            "metadata_heading", "formal_construct", "copula_def", "passive_def",
            "formula", "complexity", "compound_concept", "noun_of_noun",
            "tech_head_noun", "content_chunk"
        }


# 7. ISOLATION
def test_isolation():
    """Verify that running extraction on a single chunk produces identical results regardless of prior runs."""
    chunk = {"chunk_id": "chk_iso", "text": "Interpolation search estimates target position."}
    
    # First execution
    cands1 = extract_all_candidates_v2([chunk], max_per_chunk=1)
    
    # Intervening execution on unrelated text
    _ = extract_all_candidates_v2([{"chunk_id": "other", "text": "Different subject matter."}], max_per_chunk=1)
    
    # Second execution
    cands2 = extract_all_candidates_v2([chunk], max_per_chunk=1)

    assert len(cands1) == len(cands2)
    assert cands1[0].concept == cands2[0].concept
    assert cands1[0].canonical_key == cands2[0].canonical_key
    assert cands1[0].salience_score == cands2[0].salience_score


# 8. ARCHITECTURE ISOLATION
def test_architecture_isolation():
    """Verify that gap_candidates_v2 does NOT import DOMAIN_CONCEPTS, TECHNICAL_PATTERN, or legacy dictionaries."""
    v2_file_path = os.path.join(BASE_DIR, "apps/ai_classroom/gap_candidates_v2.py")
    with open(v2_file_path) as f:
        content = f.read()

    # Parse AST of gap_candidates_v2
    tree = ast.parse(content, filename=v2_file_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "gap_candidates" not in alias.name, f"Forbidden import of gap_candidates in {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "gap_candidates" not in mod or "gap_candidates_v2" in mod, (
                f"Forbidden from-import from gap_candidates in {mod}"
            )
            for alias in node.names:
                assert alias.name not in {"DOMAIN_CONCEPTS", "TECHNICAL_PATTERN"}, (
                    f"Forbidden import of {alias.name} from {mod}"
                )

    # Also verify imported namespace at runtime
    import apps.ai_classroom.gap_candidates_v2 as gcv2
    assert not hasattr(gcv2, "DOMAIN_CONCEPTS"), "gap_candidates_v2 must not contain DOMAIN_CONCEPTS"
    assert not hasattr(gcv2, "TECHNICAL_PATTERN"), "gap_candidates_v2 must not contain TECHNICAL_PATTERN"


# 9. ARCHITECTURE VALIDATION
def test_architecture_validation():
    """Verify Qwen schema retains IRRELEVANT and no hard relevance threshold removes candidates before Qwen."""
    from apps.ai_classroom.candidate_validation import (
        CANDIDATE_VALIDATION_SCHEMA,
        CANDIDATE_VALIDATION_GROUNDED_SCHEMA
    )
    # Both schemas must retain IRRELEVANT
    assert "IRRELEVANT" in CANDIDATE_VALIDATION_SCHEMA["properties"]["classification"]["enum"]
    assert "IRRELEVANT" in CANDIDATE_VALIDATION_GROUNDED_SCHEMA["properties"]["relevance"]["enum"]
    assert "IRRELEVANT" in CANDIDATE_VALIDATION_GROUNDED_SCHEMA["properties"]["coverage"]["enum"]

    # Verify extractor produces candidates without any hard relevance threshold
    unrelated_chunk = {"chunk_id": "chk_irrel", "text": "The Krebs cycle produces ATP and NADH in cellular respiration."}
    cands = extract_all_candidates_v2([unrelated_chunk], max_per_chunk=3)
    assert len(cands) > 0, "Extractor must not drop off-topic or irrelevant concepts prior to Qwen classification"


# 10. GROUNDED POSTCHECK DOWNGRADE RULE
def test_grounded_postcheck_downgrade_rule():
    """Verify that evaluate_grounded_postcheck correctly downgrades when quote is absent or invalid."""
    from apps.ai_classroom.candidate_validation import evaluate_grounded_postcheck

    user_note = "Binary search is an algorithm on sorted arrays that divides the search interval in half."

    # 1. Valid quote present in note -> keeps classification
    res_valid = {
        "relevance": "RELEVANT",
        "coverage": "COVERED",
        "note_quote": "divides the search interval in half",
        "reason": "Note explains halving mechanism"
    }
    cls, downgraded = evaluate_grounded_postcheck(res_valid, user_note, "halving")
    assert cls == "COVERED"
    assert not downgraded

    # 2. Quote is null / missing -> downgraded to MISSING
    res_no_quote = {
        "relevance": "RELEVANT",
        "coverage": "PARTIALLY_COVERED",
        "note_quote": None,
        "reason": "Note mentions it but omits detail"
    }
    cls, downgraded = evaluate_grounded_postcheck(res_no_quote, user_note, "time complexity")
    assert cls == "MISSING"
    assert downgraded

    # 3. Quote is hallucinated (not in note) -> downgraded to MISSING
    res_hallucinated = {
        "relevance": "RELEVANT",
        "coverage": "PARTIALLY_COVERED",
        "note_quote": "binary search takes logarithmic time O(log n)",
        "reason": "Note mentions logarithmic time"
    }
    cls, downgraded = evaluate_grounded_postcheck(res_hallucinated, user_note, "time complexity")
    assert cls == "MISSING"
    assert downgraded

    # 4. IRRELEVANT is preserved
    res_irrel = {
        "relevance": "IRRELEVANT",
        "coverage": "IRRELEVANT",
        "note_quote": None,
        "reason": "Unrelated topic"
    }
    cls, downgraded = evaluate_grounded_postcheck(res_irrel, user_note, "mitosis")
    assert cls == "IRRELEVANT"
    assert not downgraded
