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


class EntailmentVerdict(BaseModel):
    verdict: Literal["ENTAILED", "PARTIALLY_ENTAILED", "NEUTRAL", "CONTRADICTED"]
    rationale: str = ""


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

            # Support Scoring Decision Table (§3.6.2)
            if best_sim >= sup_cosine_thresh:
                # Supported regardless of lexical overlap (paraphrases covered)
                blk.support_status = "supported"
            elif best_sim >= sup_border_thresh and lex_overlap >= sup_lex_thresh:
                blk.support_status = "partial"
            elif best_sim >= sup_border_thresh and lex_overlap < sup_lex_thresh:
                # Borderline entailment check
                prompt = Prompt(
                    name="entailment_verifier",
                    version="v1",
                    user=(
                        f"Premise (Textbook Sentence):\n\"{best_sent}\"\n\n"
                        f"Hypothesis (Note Addition):\n\"{blk.text}\"\n\n"
                        "Does the textbook premise entail the note hypothesis? Output ENTAILED, PARTIALLY_ENTAILED, NEUTRAL, or CONTRADICTED."
                    ),
                )
                try:
                    res_ent = llm.generate_structured(
                        prompt=prompt,
                        schema=EntailmentVerdict,
                        request_id=f"enrich:{job_id}:support:{tid}:{repair_pass}",
                        disable_fallback=True,
                        think=False,
                    )
                    v = res_ent.data.verdict if hasattr(res_ent.data, "verdict") else res_ent.data.get("verdict", "NEUTRAL")
                except Exception:
                    v = "NEUTRAL"

                if v == "ENTAILED":
                    blk.support_status = "supported"
                elif v == "PARTIALLY_ENTAILED":
                    blk.support_status = "partial"
                else:
                    # Unsupported; drop addition
                    dropped_stats["neutral_entailment"] += 1
                    logger.info("Dropping addition in %s due to entailment verdict %s", tid, v)
                    continue
            else:
                # Similarity below borderline; drop addition
                dropped_stats["low_cosine"] += 1
                logger.info("Dropping addition in %s due to low cosine %.2f", tid, best_sim)
                continue

            blk.verification_score = round(best_sim, 4)

            # Correction-language leak check (§3.6.2a):
            # Any addition (regardless of kind) that asserts a student line is wrong
            # must go through the possible_issue path. If possible_issue is disabled,
            # the addition is dropped to prevent corrections from leaking as explanations.
            enable_possible_issue = getattr(settings, "ENRICHMENT_ENABLE_POSSIBLE_ISSUE", False)
            if isinstance(enable_possible_issue, str):
                enable_possible_issue = enable_possible_issue.lower() in ("1", "true", "yes")

            if blk.addition_kind != "possible_issue" and _contains_correction_language(blk.text):
                if enable_possible_issue:
                    # Reclassify as possible_issue and let the contradiction check below handle it
                    logger.info("Reclassifying correction-language explanation as possible_issue in %s", tid)
                    blk.addition_kind = "possible_issue"
                else:
                    # Corrections are disabled; drop the addition
                    dropped_stats["correction_leak"] += 1
                    logger.info("Dropping correction-language explanation in %s (possible_issue disabled): %.60s", tid, blk.text)
                    continue

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
