"""Render Node for Topic-Based Note Enrichment (PR 2).

Renders final Markdown notes preserving backend-assigned code vs. prose (render_as),
renumbers topic-local citations (C1..Cn) into unified ascending global references ([^1]..[^K]),
and prepares the global citation manifest.
"""
import logging
from typing import Any, Dict, List, Set, Tuple

from ai.langgraph.state.topic_enrichment_state import (
    EnrichedSection,
    EvidenceItem,
    SectionBlock,
    TopicEnrichmentState,
    TopicResearchResult,
)

logger = logging.getLogger(__name__)


def render_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute pure rendering and global citation renumbering (§3.7.1)."""
    sections_by_topic_raw = state.get("sections_by_topic", {})
    research_by_topic_raw = state.get("research_by_topic", {})
    topic_plan_raw = state.get("topic_plan") or {}

    planned_topics = topic_plan_raw.get("topics", [])
    topic_order = [t.get("topic_id") for t in planned_topics]

    # Reconstruct domain objects
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

    # 1. Global Citation Renumbering
    # Map (topic_id, local_cid) -> global_citation_number (1..K)
    global_citation_map: Dict[Tuple[str, str], int] = {}
    global_citations: List[Dict[str, Any]] = []
    citation_counter = 1

    # First pass: assign global citation numbers in document order
    for tid in topic_order:
        sec = sections.get(tid)
        if not sec:
            continue
        res = researches.get(tid)
        evidence_by_cid = {item.citation_id: item for item in (res.evidence_items if res else [])}

        for blk in sec.blocks:
            if blk.type == "addition":
                global_refs = []
                for local_cid in blk.citation_ids:
                    key = (tid, local_cid)
                    if key not in global_citation_map:
                        global_citation_map[key] = citation_counter
                        ev_item = evidence_by_cid.get(local_cid)
                        if ev_item:
                            global_citations.append({
                                "citation_number": citation_counter,
                                "source_type": ev_item.source_type,
                                "chunk_id": ev_item.chunk_id,
                                "document_id": ev_item.document_id,
                                "source_title": ev_item.source_title,
                                "chapter": ev_item.chapter,
                                "page_start": ev_item.page_start,
                                "page_end": ev_item.page_end,
                                "snippet": ev_item.snippet,
                                "dense_score": ev_item.dense_score,
                                "rrf_score": ev_item.rrf_score,
                            })
                        citation_counter += 1
                    global_refs.append(f"[^{global_citation_map[key]}]")
                # Store global citation string on block
                blk.citation_ids = global_refs

    # 2. Render Markdown Body
    md_parts: List[str] = []
    evidence_status_by_topic: Dict[str, str] = {}

    for tid in topic_order:
        sec = sections.get(tid)
        if not sec:
            continue

        evidence_status_by_topic[tid] = sec.evidence_status
        md_parts.append(f"## {sec.title}\n")

        for blk in sec.blocks:
            if blk.type == "heading":
                md_parts.append(f"### {blk.text}\n")
            elif blk.type == "student":
                if blk.render_as == "code":
                    md_parts.append(f"```\n{blk.text}\n```\n")
                else:
                    md_parts.append(f"{blk.text}\n")
            elif blk.type == "addition":
                ref_str = " ".join(blk.citation_ids)
                badge = "Correction" if blk.addition_kind == "possible_issue" else "StudyAI Note"
                md_parts.append(f"> **[{badge}]** {blk.text} {ref_str}\n")

    # 3. Append Bibliography
    if global_citations:
        md_parts.append("\n---\n### References\n")
        for cit in global_citations:
            num = cit["citation_number"]
            title = cit["source_title"]
            ch = f", Ch: {cit['chapter']}" if cit["chapter"] else ""
            pages = f", pp. {cit['page_start']}-{cit['page_end']}"
            md_parts.append(f"[^{num}]: {title}{ch}{pages}\n")

    rendered_markdown = "\n".join(md_parts).strip()

    return {
        "rendered_markdown": rendered_markdown,
        "global_citations": global_citations,
        "evidence_status_by_topic": evidence_status_by_topic,
        "sections_by_topic": {tid: sec.model_dump() for tid, sec in sections.items()},
    }
