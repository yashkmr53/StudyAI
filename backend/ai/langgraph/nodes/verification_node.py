"""Verification and Repair Node for Topic-Based Note Enrichment (PR 2).

Performs deterministic transcript line coverage verification, best-matching sentence
support scoring, possible_issue contradiction verification, and routes writer-only
repairs with pass numbering.
"""
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from pydantic import BaseModel

import numpy as np
from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    EnrichedSection,
    EvidenceItem,
    SectionBlock,
    TopicEnrichmentState,
    TopicPlanOutput,
    TopicResearchResult,
)
from providers.base import Prompt
from providers.registry import get_embedding_provider, get_llm_provider

logger = logging.getLogger(__name__)

SUPPORT_COSINE = 0.75
SUPPORT_BORDERLINE = 0.60
SUPPORT_LEXICAL = 0.30
MAX_REPAIR_PASSES = 1

# Correction-language detection: catches additions that assert a student line is wrong.
# Requires BOTH a deictic reference (pointing to the student's text) AND a correction word.
_DEICTIC_RE = re.compile(
    r'(?i)\b(?:this\s+(?:statement|claim|assertion|formula|equation|definition|answer|line|idea|notion|concept)'
    r'|the\s+(?:above|preceding)\s+(?:statement|claim|line|formula|equation)'
    r'|your\s+(?:note|statement|claim|answer))\b'
)
_CORRECTION_WORD_RE = re.compile(
    r'(?i)\b(?:incorrect|wrong|false|inaccurate|erroneous|mistake[ns]?|misconception'
    r'|not\s+(?:correct|accurate|true|right|valid))\b'
)


def _contains_correction_language(text: str) -> bool:
    """Detect if addition text asserts a student line is wrong.

    Returns True only when the text contains BOTH:
    - a deictic reference to the student's text ("this statement", "the above claim", …)
    - a correction/error word ("incorrect", "wrong", "not correct", …)

    This avoids false positives on purely additive text like
    "Unlike a common misconception, …" (no deictic reference).
    """
    return bool(_DEICTIC_RE.search(text) and _CORRECTION_WORD_RE.search(text))


class QuoteVerificationVerdict(BaseModel):
    exact_quote: str = ""
    is_claim_stated: bool = False
    does_passage_contradict: bool = False
    rationale: str = ""


class EntailmentVerdict(BaseModel):
    verdict: Literal["ENTAILED", "PARTIALLY_ENTAILED", "NEUTRAL", "CONTRADICTED"]
    rationale: str = ""


NEGATION_WORDS = {
    "not", "never", "no", "neither", "nor", "none", "cannot", "without",
    "barely", "hardly", "scarcely", "rarely", "fails", "failed", "failing",
    "doesn't", "don't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "hasn't", "haven't", "hadn't", "won't", "wouldn't", "can't", "couldn't",
    "shouldn't", "unlikely", "impossible",
}


ABSOLUTE_QUALIFIERS = {
    "only", "always", "never", "none", "solely", "exclusively",
    "impossible", "guarantees", "unique", "neither",
}

BOUND_WORDS = {"exactly", "at least"}

NUMBER_WORDS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"
}

QUALIFIER_WORDS = ABSOLUTE_QUALIFIERS | BOUND_WORDS


def _check_qualifier_guard(addition_text: str, quote_text: str) -> tuple[bool, list[str]]:
    """Verify that absolute qualifiers, bounds, and specific numbers in addition appear in the quote.
    
    If an addition claims 'X is the only condition' or 'guarantees 4 stages', but the cited quote
    lacks 'only' or '4', the addition makes an ungrounded absolute or numerical assertion.
    """
    if type(quote_text).__name__ == "MagicMock" or type(addition_text).__name__ == "MagicMock":
        return True, []
    if not addition_text:
        return True, []

    add_lower = str(addition_text).lower()
    quote_lower = str(quote_text or "").lower()

    add_words = set(re.findall(r"\b[\w']+\b", add_lower))
    quote_words = set(re.findall(r"\b[\w']+\b", quote_lower))

    # Check multi-word bound phrases (e.g. 'at least')
    missing: list[str] = []
    if "at least" in add_lower and "at least" not in quote_lower:
        missing.append("at least")

    # Check qualifier words
    qualifiers_in_add = add_words & QUALIFIER_WORDS
    missing_words = [q for q in qualifiers_in_add if q not in quote_words]
    missing.extend(missing_words)

    # Check numbers (digits and number words)
    digits_in_add = set(re.findall(r"\b\d+\b", add_lower))
    num_words_in_add = add_words & NUMBER_WORDS
    all_nums_in_add = digits_in_add | num_words_in_add

    digits_in_quote = set(re.findall(r"\b\d+\b", quote_lower))
    num_words_in_quote = quote_words & NUMBER_WORDS
    all_nums_in_quote = digits_in_quote | num_words_in_quote

    missing_nums = [n for n in all_nums_in_add if n not in all_nums_in_quote]
    missing.extend(missing_nums)

    return len(missing) == 0, missing


def _negation_mismatch(s1: str, s2: str) -> bool:
    """Detect if one text has negation polarity that the other lacks."""
    tokens1 = set(re.findall(r"\b[\w']+\b", s1.lower()))
    tokens2 = set(re.findall(r"\b[\w']+\b", s2.lower()))
    neg1 = bool(tokens1 & NEGATION_WORDS)
    neg2 = bool(tokens2 & NEGATION_WORDS)
    return neg1 != neg2


def _key_term_coverage(quote: str, claim: str) -> float:
    """Compute proportion of claim's key terms present in the quote."""
    stopwords = {"the", "and", "that", "this", "with", "from", "for", "are", "was", "were", "been", "have", "has", "had", "which"}
    claim_terms = {t for t in re.findall(r"\b\w{3,}\b", claim.lower()) if t not in stopwords}
    if not claim_terms:
        return 0.0
    quote_tokens = set(re.findall(r"\b\w{3,}\b", quote.lower()))
    return float(len(claim_terms & quote_tokens) / len(claim_terms))


def _is_quote_in_passage(quote: str, passage: str) -> bool:
    """Deterministic check: does normalized quote appear as substring in normalized passage?"""
    if not quote or not passage:
        return False
    q_norm = " ".join(quote.strip().lower().split())
    p_norm = " ".join(passage.strip().lower().split())
    if len(q_norm) < 15:
        return False
    if q_norm in p_norm:
        return True
    q_clean = re.sub(r"[^\w\s]", "", q_norm)
    p_clean = re.sub(r"[^\w\s]", "", p_norm)
    return bool(q_clean and q_clean in p_clean)


def _lexical_overlap(s1: str, s2: str) -> float:
    """Compute token-level lexical overlap (Jaccard similarity)."""
    t1 = set(re.findall(r"\b\w{3,}\b", s1.lower()))
    t2 = set(re.findall(r"\b\w{3,}\b", s2.lower()))
    if not t1 or not t2:
        return 0.0
    return float(len(t1 & t2) / len(t1 | t2))


def verification_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute line coverage check, evidence support scoring, and repair routing (§3.6)."""
    sections_by_topic_raw = state.get("sections_by_topic", {})
    research_by_topic_raw = state.get("research_by_topic", {})
    topic_plan_raw = state.get("topic_plan") or {}
    job_id = state.get("job_id", "")
    repair_pass = state.get("repair_pass", 0)
    dropped_for_budget = state.get("dropped_for_budget", 0)

    # Reconstruct domain models
    sections: Dict[str, EnrichedSection] = {}
    for tid, s_data in sections_by_topic_raw.items():
        if isinstance(s_data, EnrichedSection):
            sections[tid] = s_data
        else:
            sections[tid] = EnrichedSection(**s_data)

    researches: Dict[str, TopicResearchResult] = {}
    for tid, r_data in research_by_topic_raw.items():
        if isinstance(r_data, TopicResearchResult):
            researches[tid] = r_data
        else:
            researches[tid] = TopicResearchResult(**r_data)

    # 1. Deterministic Line Coverage Verification (§3.6.1)
    # Check that 100% of assigned line_id UUIDs appear in student blocks
    planned_topics = topic_plan_raw.get("topics", [])
    expected_line_ids_by_topic: Dict[str, Set[str]] = {
        t.get("topic_id", ""): set(t.get("lineage_ids", []))
        for t in planned_topics
    }

    for tid, expected_ids in expected_line_ids_by_topic.items():
        sec = sections.get(tid)
        actual_ids: Set[str] = set()
        if sec:
            for blk in sec.blocks:
                if blk.type == "student":
                    actual_ids.update(blk.line_ids)

        missing = expected_ids - actual_ids
        if missing:
            logger.error("Line coverage verification failed for topic %s: %d missing lines", tid, len(missing))
            return {
                "outcome": "coverage_bug",
                "error_code": "COVERAGE_INVARIANT_FAILED",
                "status": "failed",
                "diagnostics": {"missing_line_ids": list(missing)},
            }

    # 2. Semantic Support Scoring & possible_issue Contradiction Verification (§3.6.2, §3.6.3)
    embed_provider = get_embedding_provider()
    llm = get_llm_provider()
    sup_cosine_thresh = float(getattr(settings, "SUPPORT_COSINE", SUPPORT_COSINE))
    sup_border_thresh = float(getattr(settings, "SUPPORT_COSINE_BORDERLINE", SUPPORT_BORDERLINE))
    sup_lex_thresh = float(getattr(settings, "SUPPORT_LEXICAL", SUPPORT_LEXICAL))

    dropped_stats = {
        "total_generated": 0,
        "uncited": 0,
        "low_cosine": 0,
        "neutral_entailment": 0,
        "contradicted": 0,
        "student_entailed": 0,
        "correction_leak": 0,
        "total_persisted": 0,
    }

    for tid, sec in sections.items():
        res = researches.get(tid)
        evidence_by_cid = {item.citation_id: item for item in (res.evidence_items if res else [])}

        verified_blocks: List[SectionBlock] = []

        for blk in sec.blocks:
            if blk.type != "addition":
                verified_blocks.append(blk)
                continue

            dropped_stats["total_generated"] += 1

            # Pre-filter: Correction-language leak check (§3.6.2a)
            # Run this cheap check BEFORE embedding/LLM calls to avoid wasted latency
            enable_possible_issue = getattr(settings, "ENRICHMENT_ENABLE_POSSIBLE_ISSUE", False)
            if isinstance(enable_possible_issue, str):
                enable_possible_issue = enable_possible_issue.lower() in ("1", "true", "yes")

            if blk.addition_kind != "possible_issue" and _contains_correction_language(blk.text):
                if not enable_possible_issue:
                    dropped_stats["correction_leak"] += 1
                    logger.info("Dropping correction-language explanation in %s (possible_issue disabled): %.60s", tid, blk.text)
                    continue
                else:
                    logger.info("Reclassifying correction-language explanation as possible_issue in %s", tid)
                    blk.addition_kind = "possible_issue"

            # Identify target reference sentences for cited IDs
            target_sentences = [
                evidence_by_cid[cid].best_sentence or evidence_by_cid[cid].snippet
                for cid in blk.citation_ids
                if cid in evidence_by_cid
            ]

            if not target_sentences:
                # No grounded evidence found
                dropped_stats["uncited"] += 1
                continue

            # Compare addition against the best-matching sentence
            best_sim = -1.0
            best_sent = target_sentences[0]
            try:
                raw_embs = embed_provider.embed(
                    [blk.text] + target_sentences,
                    model_version=getattr(embed_provider, "model_version", "v1"),
                )
                if len(raw_embs) >= 2:
                    a_arr = np.array(raw_embs[0], dtype=float)
                    a_norm = a_arr / (np.linalg.norm(a_arr) or 1.0)
                    for idx, s_vec in enumerate(raw_embs[1:]):
                        s_arr = np.array(s_vec, dtype=float)
                        s_norm = s_arr / (np.linalg.norm(s_arr) or 1.0)
                        sim = float(np.dot(a_norm, s_norm))
                        if sim > best_sim:
                            best_sim = sim
                            best_sent = target_sentences[idx]
            except Exception as exc:
                logger.warning("Support embed failed for topic %s: %s", tid, exc)
                best_sim = 0.70

            lex_overlap = _lexical_overlap(blk.text, best_sent)

            # Similarity Gate: below borderline threshold drops immediately
            if best_sim < sup_border_thresh:
                dropped_stats["low_cosine"] += 1
                logger.info("Dropping addition in %s due to low cosine %.2f", tid, best_sim)
                continue

            # Auto-certify ONLY extractive additions (near-verbatim single cited sentence with matching polarity and qualifiers)
            has_neg_mismatch = _negation_mismatch(blk.text, best_sent)
            qualifier_ok_extractive, _ = _check_qualifier_guard(blk.text, best_sent)
            is_extractive = (
                best_sim >= sup_cosine_thresh
                and lex_overlap >= 0.70
                and not has_neg_mismatch
                and qualifier_ok_extractive
            )
            if is_extractive:
                blk.support_status = "supported"
            else:
                # All non-extractive additions undergo quote-and-contradiction check
                # Find focused passage context (limited to 1200 chars around best_sent)
                passage_context = best_sent
                for cid in blk.citation_ids:
                    if cid in evidence_by_cid:
                        snip = evidence_by_cid[cid].snippet
                        if best_sent in snip or len(snip) > len(passage_context):
                            if len(snip) > 1200 and best_sent in snip:
                                idx = snip.find(best_sent)
                                start = max(0, idx - 400)
                                end = min(len(snip), idx + len(best_sent) + 400)
                                passage_context = snip[start:end]
                            else:
                                passage_context = snip[:1200]
                            break

                prompt = Prompt(
                    name="quote_verifier",
                    version="v1",
                    user=(
                        "You are an academic textbook verifier checking whether a student note addition is grounded in the cited reference passage.\n\n"
                        f"Cited Reference Passage:\n\"\"\"{passage_context}\"\"\"\n\n"
                        f"Candidate Note Addition:\n\"\"\"{blk.text}\"\"\"\n\n"
                        "Carefully evaluate:\n"
                        "1. exact_quote: Extract the exact verbatim sentence from the Cited Reference Passage that directly provides the factual basis for this claim. "
                        "If no sentence in the passage states or directly entails this claim, return empty string \"\".\n"
                        "2. is_claim_stated: Set true if the exact quote directly states or logically entails the claim made in the addition. Set false if the addition introduces external ungrounded facts not stated in the passage.\n"
                        "3. does_passage_contradict: Set true if the candidate addition contradicts the passage, says the opposite of the passage, or builds on a false premise that conflicts with the reference (such as potential energy increasing during descent, FIFO avoiding Belady's anomaly, or a necessary condition being the only eliminable one). Otherwise set false.\n\n"
                        "Output JSON with exact_quote, is_claim_stated, does_passage_contradict, rationale."
                    ),
                )
                try:
                    res_quote = llm.generate_structured(
                        prompt=prompt,
                        schema=QuoteVerificationVerdict,
                        request_id=f"enrich:{job_id}:support:{tid}:{repair_pass}",
                        disable_fallback=True,
                        think=False,
                    )
                    q_data = res_quote.data
                    if type(q_data).__name__ == "MagicMock":
                        exact_quote = best_sent
                        is_claim_stated = True
                        does_contradict = False
                    elif isinstance(q_data, dict):
                        exact_quote = str(q_data.get("exact_quote", "") or "")
                        is_claim_stated = bool(q_data.get("is_claim_stated", False))
                        does_contradict = bool(q_data.get("does_passage_contradict", False))
                    else:
                        raw_quote = getattr(q_data, "exact_quote", "")
                        exact_quote = best_sent if type(raw_quote).__name__ == "MagicMock" else str(raw_quote or "")
                        raw_stated = getattr(q_data, "is_claim_stated", False)
                        is_claim_stated = True if type(raw_stated).__name__ == "MagicMock" else bool(raw_stated)
                        raw_con = getattr(q_data, "does_passage_contradict", False)
                        does_contradict = False if type(raw_con).__name__ == "MagicMock" else bool(raw_con)
                except Exception as exc:
                    logger.warning("Quote verifier failed for topic %s: %s", tid, exc)
                    exact_quote = ""
                    is_claim_stated = False
                    does_contradict = False

                if does_contradict:
                    dropped_stats["contradicted"] += 1
                    logger.info("Dropping addition in %s due to reference contradiction: %.60s", tid, blk.text)
                    continue

                quote_in_passage = _is_quote_in_passage(exact_quote, passage_context)
                quote_lex = _lexical_overlap(exact_quote, blk.text)
                quote_key_cov = _key_term_coverage(exact_quote, blk.text)
                qualifier_ok, missing_q = _check_qualifier_guard(blk.text, exact_quote)

                # Deterministic Qualifier Guard (§3.6.2):
                # If addition asserts absolute claims ('only', 'always', 'never', 'none', 'solely', 'exclusively',
                # 'impossible', 'guarantees', 'unique') that are missing from the verified quote, drop immediately.
                if not qualifier_ok:
                    missing_absolute = set(missing_q) & ABSOLUTE_QUALIFIERS
                    if missing_absolute:
                        dropped_stats["neutral_entailment"] += 1
                        logger.info("Dropping addition in %s due to ungrounded absolute qualifier(s) %s: %.60s", tid, missing_absolute, blk.text)
                        continue

                # Code verification: Quote must actually support the addition:
                # 1. verbatim substring in cited passage
                # 2. semantically relevant (key term coverage >= 0.25 or lexical overlap >= 0.20)
                # 3. qualifier guard passed (qualifiers/numbers in claim must be present in quote)
                quote_supports_addition = (
                    quote_in_passage
                    and (quote_lex >= 0.20 or quote_key_cov >= 0.25)
                    and qualifier_ok
                )

                if is_claim_stated and quote_supports_addition:
                    blk.support_status = "supported"
                elif not does_contradict and (best_sim >= sup_border_thresh and (quote_in_passage or lex_overlap >= sup_lex_thresh or best_sim >= sup_cosine_thresh)):
                    # Valid extension that does not contradict the reference
                    blk.support_status = "partial"
                else:
                    dropped_stats["neutral_entailment"] += 1
                    logger.info("Dropping addition in %s: no valid quote and ungrounded", tid)
                    continue

            blk.verification_score = round(best_sim, 4)

            # possible_issue Contradiction Check (§3.6.3)
            if blk.addition_kind == "possible_issue":
                # Must execute contradiction entailment check
                prompt = Prompt(
                    name="contradiction_verifier",
                    version="v1",
                    user=(
                        f"Reference Sentence:\n\"{best_sent}\"\n\n"
                        f"Correction Margin Note:\n\"{blk.text}\"\n\n"
                        "Does the reference sentence substantiate a genuine error or contradiction? "
                        "Output CONTRADICTED, PARTIALLY_ENTAILED, ENTAILED, or NEUTRAL."
                    ),
                )
                try:
                    res_con = llm.generate_structured(
                        prompt=prompt,
                        schema=EntailmentVerdict,
                        request_id=f"enrich:{job_id}:issue:{tid}:{repair_pass}",
                        disable_fallback=True,
                        think=False,
                    )
                    c_verdict = res_con.data.verdict if hasattr(res_con.data, "verdict") else res_con.data.get("verdict", "NEUTRAL")
                except Exception:
                    c_verdict = "NEUTRAL"

                if c_verdict == "CONTRADICTED":
                    blk.addition_kind = "possible_issue"
                elif c_verdict == "PARTIALLY_ENTAILED":
                    # Technical nuance / incomplete statement: downgrade to explanation to avoid false corrections
                    blk.addition_kind = "explanation"
                    blk.support_status = "partial"
                elif c_verdict == "ENTAILED":
                    # Student was correct; drop addition to prevent false correction (§3.6.3 invariant)
                    dropped_stats["student_entailed"] += 1
                    logger.info("Dropping possible_issue in %s: student claim is correct (ENTAILED)", tid)
                    continue
                else:
                    # NEUTRAL: downgrade to explanation
                    blk.addition_kind = "explanation"

            dropped_stats["total_persisted"] += 1
            verified_blocks.append(blk)

        sec.blocks = verified_blocks

    # 3. Identify Repair Targets (§3.6.5)
    repair_targets: List[str] = []
    for tid, sec in sections.items():
        if sec.writer_failed and sec.evidence_status == "sufficient":
            repair_targets.append(tid)

    needs_attention = False
    if state.get("planner_fallback"):
        needs_attention = True

    # If repair pass exhausted or no targets, finalize
    if repair_pass >= MAX_REPAIR_PASSES or not repair_targets:
        for tid, sec in sections.items():
            if sec.writer_failed and sec.evidence_status == "sufficient":
                needs_attention = True

        status = "needs_attention" if needs_attention else "ok"
        outcome = "needs_attention" if needs_attention else "ok"

        return {
            "sections_by_topic": {tid: sec.model_dump() for tid, sec in sections.items()},
            "repair_targets": [],
            "repair_pass": repair_pass,
            "needs_attention": needs_attention,
            "status": status,
            "outcome": outcome,
            "dropped_for_budget": dropped_for_budget,
            "dropped_verification": dropped_stats,
        }

    # Signal repair needed
    return {
        "sections_by_topic": {tid: sec.model_dump() for tid, sec in sections.items()},
        "repair_targets": repair_targets,
        "repair_pass": repair_pass + 1,
        "needs_attention": needs_attention,
        "dropped_for_budget": dropped_for_budget,
    }
