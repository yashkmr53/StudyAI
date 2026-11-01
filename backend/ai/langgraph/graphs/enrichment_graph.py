"""AI Topic Enrichment Pipeline (PR 2).

Orchestrates the topic-based note enrichment workflow:
1. Gating & Content Validation
2. Windowed Classification
3. Topic Planning (max 6 topics)
4. Decoupled Research & Verbatim-Student Writer (Send fan-out with dictionary reducer)
5. Sanitization & Guarded Deduplication
6. Verification & Bounded Writer-Only Repair (#pass naming)
7. Pure Markdown Rendering & Global Bibliography

Checkpoints every stage and topic in JobExecutionState with heartbeat tracking.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from django.conf import settings
from django.utils import timezone

from ai.langgraph.nodes.load_and_gate_node import load_and_gate_node
from ai.langgraph.nodes.render_node import render_node
from ai.langgraph.nodes.sanitize_dedupe_node import sanitize_and_dedupe_node
from ai.langgraph.nodes.segment_classifier_node import segment_classifier_node
from ai.langgraph.nodes.topic_planner_node import topic_planner_node
from ai.langgraph.nodes.topic_research_node import topic_research_node
from ai.langgraph.nodes.topic_writer_node import topic_writer_node
from ai.langgraph.nodes.verification_node import verification_node
from ai.langgraph.state.topic_enrichment_state import (
    EnrichedSection,
    TopicEnrichmentState,
    TopicResearchResult,
)
from apps.documents.models import Document
from apps.jobs.models import Job, JobExecutionState
from apps.profiles.models import Profile

logger = logging.getLogger(__name__)


def _checkpointed(
    stage: str,
    topic_id: str,
    job: Optional[Job],
    fn: Callable[..., Any],
    *args,
    **kwargs,
) -> Any:
    """Decorator/helper wrapping node execution with persistent DB checkpoints (§3.8.1)."""
    # 1. Update heartbeat at start of node (§3.8.1)
    if job and not topic_id:
        try:
            Job.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now())
        except Exception:
            pass

    if job:
        # 2. Check for existing checkpoint
        existing = JobExecutionState.objects.filter(
            job=job,
            completed_node=stage[:64],
            topic_id=topic_id[:64],
        ).first()

        if existing is not None:
            logger.info("Resuming stage '%s' topic '%s' from DB checkpoint", stage, topic_id)
            return existing.state_json

    # 3. Execute node function
    result = fn(*args, **kwargs)

    # 4. Save checkpoint to DB
    if job:
        try:
            # Serialize result to clean JSON-compatible dict
            if hasattr(result, "model_dump"):
                state_json = result.model_dump()
            elif isinstance(result, dict):
                state_json = copy.deepcopy(result)
            else:
                state_json = {"result": str(result)}

            JobExecutionState.objects.update_or_create(
                job=job,
                completed_node=stage[:64],
                topic_id=topic_id[:64],
                defaults={
                    "state_json": state_json,
                    "calls_used": 1,
                },
            )
            if not topic_id:
                Job.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now())
        except Exception as exc:
            logger.warning("Failed to save checkpoint for '%s' topic '%s': %s", stage, topic_id, exc)

    return result


def invoke_enrichment_graph(initial_state: Union[TopicEnrichmentState, Dict[str, Any]]) -> Dict[str, Any]:
    """Execute the full Topic Enrichment pipeline with checkpointing and bounded repair (§3.8)."""
    state: Dict[str, Any] = dict(initial_state)
    job_id = state.get("job_id")
    job = Job.objects.filter(pk=job_id).first() if job_id else None

    # Step 1: Load and Gate Node
    gate_res = _checkpointed("load_and_gate", "", job, load_and_gate_node, state)
    state.update(gate_res)
    if not state.get("is_ready", True):
        logger.info("Enrichment stopped at load_and_gate: %s", state.get("outcome"))
        return state

    # Step 2: Segment Classifier Node
    class_res = _checkpointed("classify", "", job, segment_classifier_node, state)
    state.update(class_res)
    if state.get("outcome") == "no_study_content":
        logger.info("Enrichment stopped at classify: no study content found")
        return state

    # Step 3: Topic Planner Node
    plan_res = _checkpointed("plan", "", job, topic_planner_node, state)
    state.update(plan_res)
    planned_topics = state.get("topic_plan", {}).get("topics", [])
    if not planned_topics:
        logger.info("Enrichment stopped at plan: no planned topics")
        return state

    # Resolve document & profile for research
    document_id = state.get("document_id")
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return {"outcome": "not_ready", "error_code": "DOCUMENT_NOT_FOUND"}

    profile = doc.profile
    approved_lines = state.get("approved_lines", [])
    all_lines_by_lineage = {l["lineage_id"]: l for l in approved_lines}

    concurrency = int(getattr(settings, "ENRICHMENT_CONCURRENCY", 4))
    research_by_topic: Dict[str, Any] = {}
    sections_by_topic: Dict[str, Any] = {}

    def _process_topic(topic: Dict[str, Any]) -> Tuple[str, Any, Any]:
        tid = topic.get("topic_id", "t1")
        # Research stage
        res_obj = _checkpointed(
            "research",
            tid,
            job,
            topic_research_node,
            topic=topic,
            document=doc,
            profile=profile,
            all_lines_by_lineage=all_lines_by_lineage,
        )
        if isinstance(res_obj, dict):
            res_model = TopicResearchResult(**res_obj)
        else:
            res_model = res_obj

        # Writer stage (pass 0)
        sec_obj = _checkpointed(
            "write#0",
            tid,
            job,
            topic_writer_node,
            topic=topic,
            research=res_model,
            all_lines_by_lineage=all_lines_by_lineage,
            job_id=job_id or "",
            repair_pass=0,
            llm_temperature=0.0,
        )
        return tid, res_obj, sec_obj

    # Step 4: Parallel Fan-Out (Send) with Dictionary Reducer
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_process_topic, t) for t in planned_topics]
        for f in as_completed(futures):
            tid, res_val, sec_val = f.result()
            research_by_topic[tid] = res_val.model_dump() if hasattr(res_val, "model_dump") else res_val
            sections_by_topic[tid] = sec_val.model_dump() if hasattr(sec_val, "model_dump") else sec_val

    state["research_by_topic"] = research_by_topic
    state["sections_by_topic"] = sections_by_topic

    # Step 5: Citation Sanitization & Deduplication (pass 0)
    san_res = _checkpointed("sanitize_dedupe#0", "", job, sanitize_and_dedupe_node, state)
    state.update(san_res)

    # Step 6: Verification (pass 0)
    ver_res = _checkpointed("verify#0", "", job, verification_node, state)
    state.update(ver_res)

    if state.get("outcome") == "coverage_bug":
        logger.error("Terminal coverage bug in verification; aborting note creation")
        return state

    # Step 7: Bounded Writer-Only Repair Loop (§3.6.5, §3.8.1)
    repair_targets = state.get("repair_targets", [])
    if repair_targets:
        logger.info("Executing repair pass 1 for topics: %s", repair_targets)
        topic_by_id = {t["topic_id"]: t for t in planned_topics}

        for tid in repair_targets:
            t_obj = topic_by_id.get(tid)
            if not t_obj:
                continue
            r_val = state["research_by_topic"].get(tid)
            r_model = TopicResearchResult(**r_val) if isinstance(r_val, dict) else r_val

            repaired_sec = _checkpointed(
                "write#1",
                tid,
                job,
                topic_writer_node,
                topic=t_obj,
                research=r_model,
                all_lines_by_lineage=all_lines_by_lineage,
                job_id=job_id or "",
                repair_pass=1,
                llm_temperature=0.0,
            )
            state["sections_by_topic"][tid] = (
                repaired_sec.model_dump() if hasattr(repaired_sec, "model_dump") else repaired_sec
            )

        # Re-run sanitize_dedupe and verify under pass 1
        san_res1 = _checkpointed("sanitize_dedupe#1", "", job, sanitize_and_dedupe_node, state)
        state.update(san_res1)

        ver_res1 = _checkpointed("verify#1", "", job, verification_node, state)
        state.update(ver_res1)

    # Step 8: Pure Rendering & Bibliography Assembly
    ren_res = _checkpointed("render", "", job, render_node, state)
    state.update(ren_res)

    return state
