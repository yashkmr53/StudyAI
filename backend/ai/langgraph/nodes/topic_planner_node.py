"""Topic Planner Node for Topic-Based Note Enrichment (PR 2).

Plans up to 6 distinct academic topics from classified study segments, assigning
deterministic code topic IDs ("t1".."t6"), resolving line lineage IDs, attaching
orphan lines, and providing a single-topic fallback on planner failure.
"""
import logging
from typing import Any, Dict, List, Optional, Set

from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import (
    PlannedTopic,
    TopicEnrichmentState,
    TopicPlanOutput,
)
from apps.documents.models import Document
from apps.subjects.models import Subject
from providers.base import Prompt
from providers.registry import get_llm_provider

logger = logging.getLogger(__name__)

MAX_TOPICS = 6


def _escape_xml(text: str) -> str:
    return (
        text.replace("</study_segments>", "&lt;/study_segments&gt;")
        .replace("<study_segments>", "&lt;study_segments&gt;")
    )


def topic_planner_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute topic planning (§3.2)."""
    segments = state.get("segments", [])
    approved_lines = state.get("approved_lines", [])
    document_id = state.get("document_id")

    # Gather all eligible study line items in order
    study_lines: List[Dict[str, Any]] = []
    line_by_label: Dict[str, Dict[str, Any]] = {}
    label_by_lineage: Dict[str, str] = {}

    for seg in segments:
        g_start = seg.get("global_start", 0)
        g_end = seg.get("global_end", len(approved_lines) - 1)
        for idx in range(g_start, g_end + 1):
            if idx < len(approved_lines):
                line = approved_lines[idx]
                study_lines.append(line)

    if not study_lines:
        return {
            "topic_plan": {"topics": []},
            "planner_fallback": True,
            "outcome": "no_study_content",
            "error_code": "NO_STUDY_CONTENT",
        }

    # Assign local labels L1..LN to eligible study lines
    formatted_lines = []
    for i, line in enumerate(study_lines, start=1):
        lbl = f"L{i}"
        line_by_label[lbl] = line
        label_by_lineage[line["lineage_id"]] = lbl
        escaped = _escape_xml(line.get("text", ""))
        formatted_lines.append(f"{lbl}: {escaped}")

    doc_subject_name = None
    try:
        doc = Document.objects.get(pk=document_id)
        if doc.subject:
            doc_subject_name = doc.subject.name
    except Exception:
        pass

    llm = get_llm_provider()
    prompt_body = (
        "You are an academic curriculum planner. Group the following study lines (labeled L1 to L{count}) "
        "into 1 to 6 coherent, focused technical topics.\n\n"
        "Rules:\n"
        "1. Emit at most {max_topics} topics.\n"
        "2. For each topic, provide a clear academic 'title', a 1-sentence 'description', optional 'subject', "
        "and a list of 'transcript_line_labels' (e.g. ['L1', 'L2', 'L3']).\n"
        "3. Every line should belong to the topic where it is most contextually relevant.\n\n"
        "<study_segments>\n{lines}\n</study_segments>"
    ).format(count=len(study_lines), max_topics=MAX_TOPICS, lines="\n".join(formatted_lines))

    prompt = Prompt(
        name="topic_planner",
        version="v1",
        user=prompt_body,
    )

    planned_raw_topics = []
    planner_fallback = False
    repairs_count = 0

    # Try LLM generation with bounded retries (2 attempts)
    for attempt in range(2):
        try:
            result = llm.generate_structured(
                prompt=prompt,
                schema=TopicPlanOutput,
                request_id=f"enrich:{state.get('job_id')}:plan:{attempt}",
                disable_fallback=True,
                think=False,
            )
            data = result.data
            if hasattr(data, "topics"):
                raw_topics = data.topics
            elif isinstance(data, dict):
                raw_topics = data.get("topics", [])
            else:
                raw_topics = []

            if raw_topics:
                planned_raw_topics = raw_topics
                break
        except Exception as exc:
            repairs_count += 1
            logger.warning("Topic planner attempt %d failed: %s", attempt + 1, exc)

    # Fallback to single topic if planner failed or returned empty
    if not planned_raw_topics:
        planner_fallback = True
        planned_raw_topics = [{
            "topic_id": "t1",
            "title": "Study Notes Overview",
            "description": "Comprehensive review of lecture study content.",
            "subject": doc_subject_name,
            "transcript_line_labels": [f"L{i}" for i in range(1, len(study_lines) + 1)],
        }]

    # Deterministic Normalization & Code Topic ID Assignment ("t1".."tN")
    final_topics: List[PlannedTopic] = []
    assigned_lineages: Set[str] = set()

    for idx, raw_t in enumerate(planned_raw_topics[:MAX_TOPICS], start=1):
        code_topic_id = f"t{idx}"
        if isinstance(raw_t, dict):
            title = raw_t.get("title", f"Topic {idx}").strip()
            desc = raw_t.get("description", "").strip()
            subj = raw_t.get("subject") or doc_subject_name
            labels = raw_t.get("transcript_line_labels", [])
        else:
            title = getattr(raw_t, "title", f"Topic {idx}").strip()
            desc = getattr(raw_t, "description", "").strip()
            subj = getattr(raw_t, "subject", None) or doc_subject_name
            labels = getattr(raw_t, "transcript_line_labels", [])

        # Map labels to lineage_ids, deduplicating across topics
        topic_lineages = []
        topic_labels = []
        for lbl in labels:
            lbl_clean = str(lbl).strip().upper()
            if lbl_clean in line_by_label:
                lid = line_by_label[lbl_clean]["lineage_id"]
                if lid not in assigned_lineages:
                    assigned_lineages.add(lid)
                    topic_lineages.append(lid)
                    topic_labels.append(lbl_clean)

        final_topics.append(
            PlannedTopic(
                topic_id=code_topic_id,
                title=title or f"Topic {idx}",
                description=desc or title,
                subject=subj,
                transcript_line_labels=topic_labels,
                lineage_ids=topic_lineages,
            )
        )

    # Orphan Line Attachment (§3.2):
    # If any eligible study line was omitted, attach to the nearest preceding assigned line's topic
    # (or Topic 1 if at start)
    if not final_topics:
        final_topics.append(
            PlannedTopic(
                topic_id="t1",
                title="Study Notes Overview",
                description="Comprehensive review of lecture study content.",
                subject=doc_subject_name,
                transcript_line_labels=[],
                lineage_ids=[],
            )
        )

    last_topic = final_topics[0]
    topic_by_lineage = {}
    for t in final_topics:
        for lid in t.lineage_ids:
            topic_by_lineage[lid] = t

    for line in study_lines:
        lid = line["lineage_id"]
        lbl = label_by_lineage.get(lid)
        if lid in topic_by_lineage:
            last_topic = topic_by_lineage[lid]
        else:
            # Orphan line: attach to last_topic
            last_topic.lineage_ids.append(lid)
            if lbl:
                last_topic.transcript_line_labels.append(lbl)
            assigned_lineages.add(lid)
            topic_by_lineage[lid] = last_topic

    # Prune any topics that ended up with 0 lines (unless there's only 1 topic)
    non_empty_topics = [t for t in final_topics if t.lineage_ids]
    if not non_empty_topics:
        non_empty_topics = final_topics

    # Re-index topic IDs t1..tK
    renumbered_topics = []
    for idx, t in enumerate(non_empty_topics, start=1):
        t.topic_id = f"t{idx}"
        renumbered_topics.append(t)

    plan_output = TopicPlanOutput(
        topics=renumbered_topics,
        diagnostics={
            "planner_repairs_count": repairs_count,
            "planner_fallback": planner_fallback,
            "total_study_lines": len(study_lines),
            "assigned_study_lines": len(assigned_lineages),
        },
    )

    return {
        "topic_plan": plan_output.model_dump(),
        "planner_fallback": planner_fallback,
    }
