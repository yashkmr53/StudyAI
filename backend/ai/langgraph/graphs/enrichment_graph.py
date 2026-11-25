"""AI Topic Enrichment Pipeline (PR 2).

Orchestrates the topic-based note enrichment workflow as a compiled LangGraph
StateGraph with Send() map-reduce fan-out and SQL checkpoints:
1. Gating & Content Validation
2. Windowed Classification
3. Topic Planning (max 6 topics)
4. Decoupled Research & Verbatim-Student Writer (Send fan-out with dict reducer)
5. Sanitization & Guarded Deduplication
6. Verification & Bounded Writer-Only Repair (#pass naming via Send)
7. Pure Markdown Rendering & Global Bibliography

Checkpoints every stage and topic in JobExecutionState with heartbeat tracking.
"""
import copy
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Union

from django.conf import settings
from django.db import connection, connections
from django.utils import timezone
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from ai.langgraph.nodes.load_and_gate_node import load_and_gate_node
from ai.langgraph.nodes.render_node import render_node
from ai.langgraph.nodes.sanitize_dedupe_node import sanitize_and_dedupe_node
from ai.langgraph.nodes.segment_classifier_node import segment_classifier_node
from ai.langgraph.nodes.topic_planner_node import topic_planner_node
from ai.langgraph.nodes.topic_research_node import topic_research_node
from ai.langgraph.nodes.topic_writer_node import topic_writer_node
from ai.langgraph.nodes.verification_node import verification_node
from ai.langgraph.state.topic_enrichment_state import (
    TopicEnrichmentState,
    TopicResearchResult,
)
from ai.tracing.decorators import traced_graph
from apps.documents.models import Document
from apps.jobs.models import Job, JobExecutionState

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
    if job and not topic_id:
        try:
            Job.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now())
        except Exception:
            pass

    if job:
        existing = JobExecutionState.objects.filter(
            job=job,
            completed_node=stage[:64],
            topic_id=topic_id[:64],
        ).first()

        if existing is not None:
            logger.info("Resuming stage '%s' topic '%s' from DB checkpoint", stage, topic_id)
            return existing.state_json

    result = fn(*args, **kwargs)

    if job:
        try:
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


def _job_for_state(state: Union[TopicEnrichmentState, Dict[str, Any]]) -> Optional[Job]:
    job_id = state.get("job_id")
    return Job.objects.filter(pk=job_id).first() if job_id else None


def _as_dict(val: Any) -> Dict[str, Any]:
    return val.model_dump() if hasattr(val, "model_dump") else dict(val or {})


def _close_worker_db_if_needed() -> None:
    """Release non-main worker thread PostgreSQL connections after Send execution."""
    if connection.vendor == "postgresql" and threading.current_thread() is not threading.main_thread():
        connections.close_all()


def _load_and_gate_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("load_and_gate", "", job, load_and_gate_node, state)


def _route_after_gate(state: TopicEnrichmentState) -> str:
    if not state.get("is_ready", True):
        logger.info("Enrichment stopped at load_and_gate: %s", state.get("outcome"))
        return END
    return "classify"


def _classify_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("classify", "", job, segment_classifier_node, state)


def _route_after_classify(state: TopicEnrichmentState) -> str:
    if state.get("outcome") == "no_study_content":
        logger.info("Enrichment stopped at classify: no study content found")
        return END
    return "plan"


def _plan_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("plan", "", job, topic_planner_node, state)


def _document_missing_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    return {"outcome": "not_ready", "error_code": "DOCUMENT_NOT_FOUND"}


def _fanout_topics(state: TopicEnrichmentState) -> Union[str, List[Send]]:
    planned_topics = (state.get("topic_plan") or {}).get("topics", [])
    if not planned_topics:
        logger.info("Enrichment stopped at plan: no planned topics")
        return END

    document_id = state.get("document_id")
    if not Document.objects.filter(pk=document_id).exists():
        return "document_missing"

    approved_lines = state.get("approved_lines", [])
    all_lines_by_lineage = {line["lineage_id"]: line for line in approved_lines}
    job_id = state.get("job_id") or ""
    return [
        Send(
            "topic_worker",
            {
                "document_id": document_id,
                "job_id": job_id,
                "topic": topic,
                "all_lines_by_lineage": all_lines_by_lineage,
            },
        )
        for topic in planned_topics
    ]


def _topic_worker_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    document_id = payload["document_id"]
    job_id = payload.get("job_id") or ""
    topic = payload["topic"]
    all_lines_by_lineage = payload.get("all_lines_by_lineage", {})

    doc = Document.objects.select_related("profile", "subject").get(pk=document_id)
    profile = doc.profile
    job = Job.objects.filter(pk=job_id).first() if job_id else None

    if profile:
        from shared.database.rls import bind_profile_session, clear_profile_context

        bind_profile_session(profile.id)
    try:
        tid = topic.get("topic_id", "t1")
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
        res_model = TopicResearchResult(**res_obj) if isinstance(res_obj, dict) else res_obj
        sec_obj = _checkpointed(
            "write#0",
            tid,
            job,
            topic_writer_node,
            topic=topic,
            research=res_model,
            all_lines_by_lineage=all_lines_by_lineage,
            job_id=job_id,
            repair_pass=0,
            llm_temperature=0.0,
        )
        return {
            "research_by_topic": {tid: _as_dict(res_obj)},
            "sections_by_topic": {tid: _as_dict(sec_obj)},
        }
    finally:
        if profile:
            clear_profile_context()
        _close_worker_db_if_needed()


def _sanitize_dedupe_pass0_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("sanitize_dedupe#0", "", job, sanitize_and_dedupe_node, state)


def _verify_pass0_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("verify#0", "", job, verification_node, state)


def _route_after_verify0(state: TopicEnrichmentState) -> Union[str, List[Send]]:
    if state.get("outcome") == "coverage_bug":
        logger.error("Terminal coverage bug in verification; aborting note creation")
        return END

    repair_targets = state.get("repair_targets", [])
    if repair_targets:
        planned_topics = (state.get("topic_plan") or {}).get("topics", [])
        topic_by_id = {t["topic_id"]: t for t in planned_topics}
        approved_lines = state.get("approved_lines", [])
        all_lines_by_lineage = {line["lineage_id"]: line for line in approved_lines}
        research_by_topic = state.get("research_by_topic", {})
        job_id = state.get("job_id") or ""
        sends = [
            Send(
                "repair_worker",
                {
                    "job_id": job_id,
                    "document_id": state.get("document_id"),
                    "profile_id": state.get("profile_id"),
                    "topic": topic_by_id[tid],
                    "research_dict": research_by_topic.get(tid),
                    "all_lines_by_lineage": all_lines_by_lineage,
                },
            )
            for tid in repair_targets
            if tid in topic_by_id
        ]
        if sends:
            logger.info("Executing repair pass 1 via Send for topics: %s", repair_targets)
            return sends
    return "render"


def _repair_worker_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id = payload.get("job_id") or ""
    topic = payload["topic"]
    tid = topic["topic_id"]
    all_lines_by_lineage = payload.get("all_lines_by_lineage", {})
    r_val = payload.get("research_dict")
    r_model = TopicResearchResult(**r_val) if isinstance(r_val, dict) else r_val
    job = Job.objects.filter(pk=job_id).first() if job_id else None

    profile_id = payload.get("profile_id")
    if not profile_id and payload.get("document_id"):
        profile_id = Document.objects.filter(pk=payload["document_id"]).values_list("profile_id", flat=True).first()

    if profile_id:
        from shared.database.rls import bind_profile_session, clear_profile_context

        bind_profile_session(profile_id)
    try:
        repaired_sec = _checkpointed(
            "write#1",
            tid,
            job,
            topic_writer_node,
            topic=topic,
            research=r_model,
            all_lines_by_lineage=all_lines_by_lineage,
            job_id=job_id,
            repair_pass=1,
            llm_temperature=0.0,
        )
        return {"sections_by_topic": {tid: _as_dict(repaired_sec)}}
    finally:
        if profile_id:
            clear_profile_context()
        _close_worker_db_if_needed()


def _sanitize_dedupe_pass1_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("sanitize_dedupe#1", "", job, sanitize_and_dedupe_node, state)


def _verify_pass1_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("verify#1", "", job, verification_node, state)


def _render_stage(state: TopicEnrichmentState) -> Dict[str, Any]:
    job = _job_for_state(state)
    return _checkpointed("render", "", job, render_node, state)


def build_enrichment_graph():
    """Compile the LangGraph Topic Enrichment StateGraph with Send() map-reduce."""
    graph = StateGraph(TopicEnrichmentState)

    graph.add_node("load_and_gate", _load_and_gate_stage)
    graph.add_node("classify", _classify_stage)
    graph.add_node("plan", _plan_stage)
    graph.add_node("document_missing", _document_missing_stage)
    graph.add_node("topic_worker", _topic_worker_stage)
    graph.add_node("sanitize_dedupe_pass0", _sanitize_dedupe_pass0_stage)
    graph.add_node("verify_pass0", _verify_pass0_stage)
    graph.add_node("repair_worker", _repair_worker_stage)
    graph.add_node("sanitize_dedupe_pass1", _sanitize_dedupe_pass1_stage)
    graph.add_node("verify_pass1", _verify_pass1_stage)
    graph.add_node("render", _render_stage)

    graph.set_entry_point("load_and_gate")
    graph.add_conditional_edges(
        "load_and_gate",
        _route_after_gate,
        {"classify": "classify", END: END},
    )
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"plan": "plan", END: END},
    )
    graph.add_conditional_edges(
        "plan",
        _fanout_topics,
        ["topic_worker", "document_missing", END],
    )
    graph.add_edge("document_missing", END)
    graph.add_edge("topic_worker", "sanitize_dedupe_pass0")
    graph.add_edge("sanitize_dedupe_pass0", "verify_pass0")
    graph.add_conditional_edges(
        "verify_pass0",
        _route_after_verify0,
        ["repair_worker", "render", END],
    )
    graph.add_edge("repair_worker", "sanitize_dedupe_pass1")
    graph.add_edge("sanitize_dedupe_pass1", "verify_pass1")
    graph.add_edge("verify_pass1", "render")
    graph.add_edge("render", END)

    return graph.compile()


enrichment_graph = build_enrichment_graph()


@traced_graph("studyai.enrichment.graph", feature="enrichment")
def invoke_enrichment_graph(initial_state: Union[TopicEnrichmentState, Dict[str, Any]]) -> Dict[str, Any]:
    """Execute the full Topic Enrichment pipeline with checkpointing and bounded repair (§3.8)."""
    concurrency = 1 if connection.vendor == "sqlite" else max(1, int(getattr(settings, "ENRICHMENT_CONCURRENCY", 4)))
    return enrichment_graph.invoke(dict(initial_state), config={"max_concurrency": concurrency})
