"""Sanitize and Deduplicate Node for Topic-Based Note Enrichment (PR 2).

Validates individual addition citations against evidence manifests, strips ungrounded
citations, drops ungrounded additions, and performs cross-topic guarded deduplication
with MAX_DEDUPE_PAIRS capping and keep_both support.
"""
import logging
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from pydantic import BaseModel, Field

import numpy as np
from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    EnrichedSection,
    EvidenceItem,
    SectionBlock,
    TopicEnrichmentState,
    TopicResearchResult,
)
from providers.base import Prompt
from providers.registry import get_embedding_provider, get_llm_provider

logger = logging.getLogger(__name__)


class DedupeProposal(BaseModel):
    decision: Literal["keep_first", "keep_second", "merge", "keep_both"]
    merged_text: Optional[str] = None
    rationale: str = ""


def sanitize_and_dedupe_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute citation sanitization and cross-topic deduplication (§3.5)."""
    sections_by_topic_raw = state.get("sections_by_topic", {})
    research_by_topic_raw = state.get("research_by_topic", {})
    job_id = state.get("job_id", "")
    repair_pass = state.get("repair_pass", 0)

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

    # 1. Individual Citation Sanitization (§3.5)
    for tid, sec in sections.items():
        res = researches.get(tid)
        valid_cits = {item.citation_id for item in res.evidence_items} if res else set()

        sanitized_blocks: List[SectionBlock] = []
        for blk in sec.blocks:
            if blk.type == "addition":
                grounded_cits = [c for c in blk.citation_ids if c in valid_cits]
                if not grounded_cits:
                    # Drop ungrounded addition individually
                    logger.info("Dropping ungrounded addition in topic %s (pass %d)", tid, repair_pass)
                    continue
                blk.citation_ids = grounded_cits
            sanitized_blocks.append(blk)
        sec.blocks = sanitized_blocks

    # 2. Guarded Deduplication Across Topics (§3.5)
    dup_cosine = float(getattr(settings, "DUP_COSINE", 0.88))
    max_dedupe_pairs = int(getattr(settings, "MAX_DEDUPE_PAIRS", 6))

    # Collect all addition blocks across all topics
    addition_items: List[Tuple[str, int, SectionBlock]] = []  # (topic_id, block_index, block)
    for tid, sec in sorted(sections.items()):
        for idx, blk in enumerate(sec.blocks):
            if blk.type == "addition":
                addition_items.append((tid, idx, blk))

    dropped_for_budget = state.get("dropped_for_budget", 0)
    dedupe_pairs_evaluated = 0

    if len(addition_items) >= 2:
        embed_provider = get_embedding_provider()
        addition_texts = [item[2].text for item in addition_items]
        try:
            embs_raw = embed_provider.embed(addition_texts)
            norm_embs = []
            for vec in embs_raw:
                arr = np.array(vec, dtype=float)
                norm_embs.append(arr / (np.linalg.norm(arr) or 1.0))
        except Exception as exc:
            logger.warning("Failed to embed additions for deduplication: %s", exc)
            norm_embs = []

        candidate_pairs: List[Tuple[float, int, int]] = []
        if norm_embs and len(norm_embs) == len(addition_items):
            for i in range(len(addition_items)):
                for j in range(i + 1, len(addition_items)):
                    tid_i = addition_items[i][0]
                    tid_j = addition_items[j][0]
                    # Only deduplicate across DIFFERENT topics
                    if tid_i == tid_j:
                        continue
                    sim = float(np.dot(norm_embs[i], norm_embs[j]))
                    if sim >= dup_cosine:
                        candidate_pairs.append((sim, i, j))

        # Sort descending by similarity and cap at MAX_DEDUPE_PAIRS
        candidate_pairs.sort(key=lambda x: x[0], reverse=True)
        eval_pairs = candidate_pairs[:max_dedupe_pairs]

        llm = get_llm_provider()
        to_delete_additions: Set[Tuple[str, int]] = set()

        for sim, i, j in eval_pairs:
            dedupe_pairs_evaluated += 1
            tid_i, idx_i, blk_i = addition_items[i]
            tid_j, idx_j, blk_j = addition_items[j]

            if (tid_i, idx_i) in to_delete_additions or (tid_j, idx_j) in to_delete_additions:
                continue

            prompt_body = (
                "You are an academic editor reviewing two similar supplementary notes from different sections.\n"
                "Addition 1 (Topic {t1}): \"{text1}\"\n"
                "Addition 2 (Topic {t2}): \"{text2}\"\n\n"
                "Determine how to handle the duplication:\n"
                "- 'keep_both': Both additions provide distinct, complementary insights despite similar wording.\n"
                "- 'keep_first': Keep Addition 1, drop Addition 2.\n"
                "- 'keep_second': Keep Addition 2, drop Addition 1.\n"
                "- 'merge': Merge into a single concise addition to replace Addition 1 (Addition 2 dropped).\n"
            ).format(
                t1=tid_i,
                text1=blk_i.text.replace('"', '\\"'),
                t2=tid_j,
                text2=blk_j.text.replace('"', '\\"'),
            )

            prompt = Prompt(
                name="deduplication",
                version="v1",
                user=prompt_body,
            )

            try:
                res = llm.generate_structured(
                    prompt=prompt,
                    schema=DedupeProposal,
                    request_id=f"enrich:{job_id}:dedupe:{tid_i}_{tid_j}:{repair_pass}",
                    disable_fallback=True,
                    think=False,
                )
                data = res.data
                decision = data.decision if hasattr(data, "decision") else data.get("decision", "keep_both")
                merged_text = data.merged_text if hasattr(data, "merged_text") else data.get("merged_text")
            except Exception as exc:
                logger.warning("Deduplication LLM call failed: %s; keeping both", exc)
                decision = "keep_both"
                merged_text = None

            if decision == "keep_first":
                to_delete_additions.add((tid_j, idx_j))
            elif decision == "keep_second":
                to_delete_additions.add((tid_i, idx_i))
            elif decision == "merge":
                # Replace blk_i text and merge citations from blk_j
                if merged_text and merged_text.strip():
                    blk_i.text = merged_text.strip()
                # Citations must be unioned (§3.5 invariant)
                union_cits = sorted(list(set(blk_i.citation_ids + blk_j.citation_ids)))
                blk_i.citation_ids = union_cits
                to_delete_additions.add((tid_j, idx_j))
            elif decision == "keep_both":
                pass  # Keep both intact (§3.5 invariant)

        # Apply deletions
        if to_delete_additions:
            for tid, sec in sections.items():
                sec.blocks = [
                    blk for idx, blk in enumerate(sec.blocks)
                    if (tid, idx) not in to_delete_additions
                ]

    # Convert back to dicts for state serialization
    return {
        "sections_by_topic": {tid: sec.model_dump() for tid, sec in sections.items()},
        "dedupe_pairs_evaluated": dedupe_pairs_evaluated,
        "dropped_for_budget": dropped_for_budget,
    }
