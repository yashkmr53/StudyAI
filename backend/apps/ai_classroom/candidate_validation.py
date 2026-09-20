"""Qwen validation for gap candidates.

This module provides a focused LLM prompt that asks Qwen to validate
specific candidate concepts rather than discover gaps from scratch.
"""
from typing import Any, Dict, List, Optional
import json
from apps.ai_classroom.prompts import active_prompt
from providers.base import Prompt
from providers.registry import get_llm_provider


CANDIDATE_VALIDATION_SCHEMA = {
    "type": "object",
    "required": ["classification", "reason", "missing_from_note", "evidence_in_reference"],
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["MISSING", "PARTIALLY_COVERED", "COVERED", "IRRELEVANT"],
            "description": "Classification of the candidate concept relative to the student note"
        },
        "reason": {
            "type": "string",
            "description": "Explanation of why this classification was assigned"
        },
        "missing_from_note": {
            "type": "string",
            "description": "What specific aspect of the candidate concept is missing from the note, if any"
        },
        "evidence_in_reference": {
            "type": "string",
            "description": "Quote or summary from reference evidence supporting the candidate concept"
        }
    }
}

# 3-way coverage schema (Architecture D) - no IRRELEVANT
CANDIDATE_COVERAGE_SCHEMA = {
    "type": "object",
    "required": ["classification", "reason", "missing_from_note", "evidence_in_reference"],
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["MISSING", "PARTIALLY_COVERED", "COVERED"],
            "description": "Coverage classification of the candidate concept (relevance pre-filtered)"
        },
        "reason": {
            "type": "string",
            "description": "Explanation of why this coverage classification was assigned"
        },
        "missing_from_note": {
            "type": "string",
            "description": "What specific aspect of the candidate concept is missing from the note, if any"
        },
        "evidence_in_reference": {
            "type": "string",
            "description": "Quote or summary from reference evidence supporting the candidate concept"
        }
    }
}


CANDIDATE_VALIDATION_PROMPT_V1 = (
    "You are evaluating whether a specific concept is genuinely missing from a student's study note.\n\n"
    "USER NOTE:\n{user_note}\n\n"
    "CANDIDATE CONCEPT:\n{candidate_concept}\n\n"
    "REFERENCE EVIDENCE:\n{reference_evidence}\n\n"
    "TASK: Determine if this candidate concept is:\n"
    "  - MISSING: The concept is relevant to understanding the note and is absent or materially underdeveloped\n"
    "  - PARTIALLY_COVERED: The concept is mentioned but lacks important detail/explanation\n"
    "  - COVERED: The concept is adequately explained in the note\n"
    "  - IRRELEVANT: The concept is not relevant to the note's topic\n\n"
    "CRITICAL RULES:\n"
    "  - A concept is MISSING if the note does not meaningfully address it\n"
    "  - A concept is PARTIALLY_COVERED if the note mentions keywords but lacks the core idea\n"
    "  - Do not mark as MISSING if the note already adequately covers the concept\n"
    "  - Do not mark as MISSING if the concept is tangentially related but not core to understanding\n\n"
    "Respond with ONLY valid JSON:\n"
    '{{"classification": "MISSING|PARTIALLY_COVERED|COVERED|IRRELEVANT", "reason": "...", "missing_from_note": "...", "evidence_in_reference": "..."}}'
)

# Prompt B: Improved version with explicit decision rules preventing reference confusion
CANDIDATE_VALIDATION_PROMPT_V2 = (
    "You are evaluating whether a candidate concept is missing from a student's study note based on reference evidence.\n\n"
    "STUDENT NOTE:\n{user_note}\n\n"
    "CANDIDATE CONCEPT:\n{candidate_concept}\n\n"
    "REFERENCE EVIDENCE:\n{reference_evidence}\n\n"
    "TASK: Determine whether the STUDENT NOTE contains the candidate concept.\n"
    "Important: The reference evidence always contains the candidate concept. You are evaluating the STUDENT NOTE.\n\n"
    "DECISION RULES (Select exactly one classification):\n"
    "  - COVERED:\n"
    "    The note already explains the candidate sufficiently.\n"
    "  - PARTIALLY_COVERED:\n"
    "    The concept is mentioned, but an important aspect is missing.\n"
    "  - MISSING:\n"
    "    The concept is relevant to the note, supported by the reference evidence, and materially absent from the note.\n"
    "  - IRRELEVANT:\n"
    "    The candidate is not sufficiently relevant to the note.\n\n"
    "Respond with ONLY valid JSON."
)

# Grounded prompt for Arm C and ORACLE arms with quote verification and downgrade rule
CANDIDATE_VALIDATION_GROUNDED_SCHEMA = {
    "type": "object",
    "required": ["relevance", "coverage", "note_quote", "reason"],
    "properties": {
        "relevance": {
            "type": "string",
            "enum": ["RELEVANT", "IRRELEVANT"],
            "description": "Whether the concept is relevant to the note's subject"
        },
        "coverage": {
            "type": "string",
            "enum": ["COVERED", "PARTIALLY_COVERED", "MISSING", "IRRELEVANT"],
            "description": "Coverage classification of the candidate concept"
        },
        "note_quote": {
            "type": ["string", "null"],
            "description": "Verbatim quote from student note where concept is mentioned, or null if absent"
        },
        "reason": {
            "type": "string",
            "description": "Explanation of the classification"
        }
    }
}

CANDIDATE_VALIDATION_PROMPT_GROUNDED = (
    "You are evaluating whether a candidate concept is missing from a student's study note based on reference evidence.\n\n"
    "STUDENT NOTE:\n{user_note}\n\n"
    "CANDIDATE CONCEPT:\n{candidate_concept}\n\n"
    "REFERENCE EVIDENCE:\n{reference_evidence}\n\n"
    "TASK: Determine whether the STUDENT NOTE covers the candidate concept.\n\n"
    "DECISION RULES:\n"
    "  - COVERED: The note states the candidate concept's core claim; extra detail in the reference chunk does not make it partial.\n"
    "  - PARTIALLY_COVERED: The candidate concept itself is explicitly mentioned in the note, but omits an important part.\n"
    "  - MISSING: The concept is relevant to the note's subject but the note does not state the concept.\n"
    "  - IRRELEVANT: The concept is a separate topic, not an aspect of the note's subject. Not being mentioned in the note is never a reason for IRRELEVANT, and presence in the reference is not evidence of relevance.\n\n"
    "NOTE_QUOTE RULES:\n"
    "  - If COVERED or PARTIALLY_COVERED, you MUST provide a verbatim quote from the student note showing where the CANDIDATE CONCEPT ('{candidate_concept}') is mentioned.\n"
    "  - If the candidate concept ('{candidate_concept}') does not appear anywhere in the student note, you MUST set note_quote to null, and coverage MUST be MISSING. Do NOT quote unrelated sentences from the note.\n\n"
    "Respond with ONLY valid JSON with this exact structure:\n"
    '{{"relevance": "RELEVANT|IRRELEVANT", "coverage": "COVERED|PARTIALLY_COVERED|MISSING|IRRELEVANT", "note_quote": null, "reason": "..."}}'
)

# Architecture D: 3-way coverage classifier (relevance handled separately)
# This prompt is used AFTER the relevance gate has filtered to only RELEVANT candidates
CANDIDATE_COVERAGE_PROMPT_V1 = (
    "You are evaluating how well a student's study note covers a specific concept.\n\n"
    "STUDENT NOTE:\n{user_note}\n\n"
    "CANDIDATE CONCEPT:\n{candidate_concept}\n\n"
    "REFERENCE EVIDENCE:\n{reference_evidence}\n\n"
    "IMPORTANT: This candidate has already been verified as RELEVANT to the note.\n"
    "Your task is to assess COVERAGE ONLY - do not judge relevance.\n\n"
    "DECISION RULES (Select exactly one):\n"
    "  - COVERED:\n"
    "    The note adequately explains the concept for its current scope.\n"
    "    The core idea, key details, and implications are present.\n"
    "  - PARTIALLY_COVERED:\n"
    "    The note explicitly addresses the concept, but omits a substantive aspect\n"
    "    that is present in the reference evidence (e.g., missing key detail,\n"
    "    missing proof/justification, missing specific cases, missing formula).\n"
    "  - MISSING:\n"
    "    The note contains no meaningful explanation of the concept.\n"
    "    The concept is not addressed at all, or only mentioned in passing\n"
    "    without any substantive content.\n\n"
    "EXAMPLES:\n"
    "  COVERED: Note says 'Dijkstra uses a priority queue to select nodes' -> candidate 'priority queue'\n"
    "  PARTIALLY_COVERED: Note mentions 'rotations' but omits the 4 AVL rotation cases -> candidate 'AVL rotations'\n"
    "  MISSING: Note describes Dijkstra but never mentions time complexity -> candidate 'time complexity'\n\n"
    "Respond with ONLY valid JSON:\n"
    '{{\"classification\": \"MISSING|PARTIALLY_COVERED|COVERED\", \"reason\": \"...\", \"missing_from_note\": \"...\", \"evidence_in_reference\": \"...\"}}'
)

CANDIDATE_VALIDATION_PROMPT = CANDIDATE_VALIDATION_PROMPT_V1


def validate_candidate_with_qwen(
    user_note: str,
    candidate_concept: str,
    reference_evidence: str,
    llm_provider=None,
    prompt_version: str = "v1"
) -> Dict[str, Any]:
    """Validate a single candidate concept using Qwen (4-way: includes IRRELEVANT)."""
    if llm_provider is None:
        llm_provider = get_llm_provider()
    
    template = CANDIDATE_VALIDATION_PROMPT_V2 if prompt_version in ("v2", "b", "B") else CANDIDATE_VALIDATION_PROMPT_V1
    
    prompt_text = template.format(
        user_note=user_note,
        candidate_concept=candidate_concept,
        reference_evidence=reference_evidence
    )
    
    prompt = Prompt(
        name="gap_candidate_validation",
        version=prompt_version,
        user=prompt_text,
    )
    
    result = llm_provider.generate_structured(
        prompt=prompt,
        schema=CANDIDATE_VALIDATION_SCHEMA,
        request_id=f"gap_validation:{candidate_concept[:32]}",
        disable_fallback=True,
    )
    
    # Parse the response - handle both dict and string responses
    data = result.data
    if isinstance(data, dict):
        parsed = data
    else:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, AttributeError):
            parsed = {
                "classification": "MISSING",
                "reason": "Failed to parse LLM response",
                "missing_from_note": "",
                "evidence_in_reference": ""
            }
    
    # Normalize classification contract (§5)
    valid_classes = {"MISSING", "PARTIALLY_COVERED", "COVERED", "IRRELEVANT"}
    raw_class = str(parsed.get("classification", "")).upper().strip()
    if raw_class in valid_classes:
        parsed["classification"] = raw_class
    elif "PARTIAL" in raw_class:
        parsed["classification"] = "PARTIALLY_COVERED"
    elif "COVER" in raw_class and "NOT" not in raw_class:
        parsed["classification"] = "COVERED"
    elif "IRRELEVANT" in raw_class or "NOT RELEVANT" in raw_class:
        parsed["classification"] = "IRRELEVANT"
    else:
        parsed["classification"] = "MISSING"
        
    return parsed


def validate_candidate_coverage(
    user_note: str,
    candidate_concept: str,
    reference_evidence: str,
    llm_provider=None
) -> Dict[str, Any]:
    """Validate coverage for a RELEVANT candidate (3-way: MISSING, PARTIALLY_COVERED, COVERED).
    
    This is used in Architecture D where relevance has already been determined.
    """
    if llm_provider is None:
        llm_provider = get_llm_provider()
    
    prompt_text = CANDIDATE_COVERAGE_PROMPT_V1.format(
        user_note=user_note,
        candidate_concept=candidate_concept,
        reference_evidence=reference_evidence
    )
    
    prompt = Prompt(
        name="gap_candidate_coverage",
        version="v1",
        user=prompt_text,
    )
    
    result = llm_provider.generate_structured(
        prompt=prompt,
        schema=CANDIDATE_COVERAGE_SCHEMA,
        request_id=f"gap_coverage:{candidate_concept[:32]}",
        disable_fallback=True,
    )
    
    # Parse the response
    data = result.data
    if isinstance(data, dict):
        parsed = data
    else:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, AttributeError):
            parsed = {
                "classification": "MISSING",
                "reason": "Failed to parse LLM response",
                "missing_from_note": "",
                "evidence_in_reference": ""
            }
    
    # Normalize - only 3 valid classes now
    valid_classes = {"MISSING", "PARTIALLY_COVERED", "COVERED"}
    raw_class = str(parsed.get("classification", "")).upper().strip()
    if raw_class in valid_classes:
        parsed["classification"] = raw_class
    elif "PARTIAL" in raw_class:
        parsed["classification"] = "PARTIALLY_COVERED"
    elif "COVER" in raw_class and "NOT" not in raw_class:
        parsed["classification"] = "COVERED"
    else:
        parsed["classification"] = "MISSING"
        
    return parsed


def validate_candidates_batch(
    user_note: str,
    candidates: list,
    reference_chunks: Dict[str, str],
    llm_provider=None,
    prompt_version: str = "v2"
) -> list:
    """Validate multiple candidates in batch (individual calls for now)."""
    results = []
    for candidate in candidates:
        chunk_id = candidate.source_chunk_id
        evidence = reference_chunks.get(chunk_id, candidate.source_content)
        
        validation = validate_candidate_with_qwen(
            user_note=user_note,
            candidate_concept=candidate.concept,
            reference_evidence=evidence,
            llm_provider=llm_provider,
            prompt_version=prompt_version
        )
        
        results.append({
            'candidate': candidate,
            'validation': validation
        })
    
    return results


def evaluate_grounded_postcheck(
    raw_result: Dict[str, Any],
    user_note: str,
    candidate_concept: str = ""
) -> Tuple[str, bool]:
    """Apply post-check in code:
    If coverage is COVERED/PARTIALLY_COVERED and note_quote is not a whitespace-normalised,
    casefolded substring of the note, downgrade to MISSING and log the downgrade.
    Returns (final_classification, was_downgraded).
    """
    relevance = str(raw_result.get("relevance", "")).upper().strip()
    coverage = str(raw_result.get("coverage", "")).upper().strip()
    quote = raw_result.get("note_quote")

    if relevance == "IRRELEVANT" or coverage == "IRRELEVANT":
        return "IRRELEVANT", False

    valid_classes = {"MISSING", "PARTIALLY_COVERED", "COVERED"}
    if coverage not in valid_classes:
        if "PARTIAL" in coverage:
            coverage = "PARTIALLY_COVERED"
        elif "COVER" in coverage and "NOT" not in coverage:
            coverage = "COVERED"
        else:
            coverage = "MISSING"

    was_downgraded = False
    if coverage in ("COVERED", "PARTIALLY_COVERED"):
        if not quote or not isinstance(quote, str):
            coverage = "MISSING"
            was_downgraded = True
        else:
            norm_quote = " ".join(quote.casefold().split())
            norm_note = " ".join(user_note.casefold().split())
            if not norm_quote or norm_quote in ("null", "none", "n/a", "not mentioned", "empty") or norm_quote not in norm_note:
                coverage = "MISSING"
                was_downgraded = True

    return coverage, was_downgraded


def validate_candidate_grounded(
    user_note: str,
    candidate_concept: str,
    reference_evidence: str,
    llm_provider=None
) -> Dict[str, Any]:
    """Validate a candidate concept using the Grounded Prompt (Arm C / ORACLE)."""
    if llm_provider is None:
        llm_provider = get_llm_provider()

    prompt_text = CANDIDATE_VALIDATION_PROMPT_GROUNDED.format(
        user_note=user_note,
        candidate_concept=candidate_concept,
        reference_evidence=reference_evidence
    )

    prompt = Prompt(
        name="gap_candidate_validation_grounded",
        version="v1",
        user=prompt_text,
    )

    result = llm_provider.generate_structured(
        prompt=prompt,
        schema=CANDIDATE_VALIDATION_GROUNDED_SCHEMA,
        request_id=f"gap_grounded:{candidate_concept[:32]}",
        disable_fallback=True,
    )

    data = result.data
    if isinstance(data, dict):
        parsed = data
    else:
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, AttributeError):
            parsed = {
                "relevance": "RELEVANT",
                "coverage": "MISSING",
                "note_quote": None,
                "reason": "Failed to parse LLM response"
            }

    final_class, was_downgraded = evaluate_grounded_postcheck(
        parsed, user_note, candidate_concept
    )
    parsed["classification"] = final_class
    parsed["downgraded"] = was_downgraded
    return parsed


def validate_candidates_batch_coverage(
    user_note: str,
    candidates: list,
    reference_chunks: Dict[str, str],
    llm_provider=None
) -> list:
    """Validate coverage for multiple RELEVANT candidates (Architecture D).
    
    This is the 3-way coverage classifier used after relevance gate.
    """
    results = []
    for candidate in candidates:
        chunk_id = candidate.source_chunk_id
        evidence = reference_chunks.get(chunk_id, candidate.source_content)
        
        validation = validate_candidate_coverage(
            user_note=user_note,
            candidate_concept=candidate.concept,
            reference_evidence=evidence,
            llm_provider=llm_provider
        )
        
        results.append({
            'candidate': candidate,
            'validation': validation
        })
    
    return results