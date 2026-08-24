"""Agent Telemetry (Phase 1).

Records execution traces and emits metrics.
"""
import logging

from django.conf import settings
from django.db import transaction

from apps.agents.models import AgentExecutionLog
from shared.observability.metrics import incr

logger = logging.getLogger(__name__)


def record_agent_execution(
    *,
    request_id: str,
    profile,
    intent_category: str,
    model_provider: str,
    model_name: str,
    prompt_version: str,
    tool_calls: list[dict],
    iterations: int,
    retrieved_evidence_ids: list[str],
    total_tokens: int,
    total_latency_ms: int,
    outcome: str,
    citation_verification_status: str | None = None,
    citation_verification_score: float | None = None,
    guardrail_violations: int = 0,
) -> AgentExecutionLog:
    """Persist agent execution log and emit metrics."""
    try:
        with transaction.atomic():
            log = AgentExecutionLog.objects.create(
                request_id=request_id,
                profile=profile,
                intent_category=intent_category,
                model_provider=model_provider,
                model_name=model_name,
                prompt_version=prompt_version,
                tool_call_sequence=tool_calls,
                iterations=iterations,
                retrieved_evidence_ids=retrieved_evidence_ids,
                total_tokens=total_tokens,
                total_latency_ms=total_latency_ms,
                outcome=outcome,
                citation_verification_status=citation_verification_status,
                guardrail_violations=guardrail_violations,
            )

        # Emit Prometheus metrics
        incr(f"agent_executions_total", 1)
        incr(f"agent_executions_total.{outcome}", 1)
        incr(f"agent_tool_calls_total", len(tool_calls))
        for tc in tool_calls:
            incr(f"agent_tool_calls_total.{tc.get('tool', 'unknown')}.{str(tc.get('success', False)).lower()}", 1)

        return log

    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to record agent execution: %s", exc)
        # Don't raise — telemetry must not break the pipeline
        return None


def classify_intent(user_request: str) -> str:
    """Simple intent classification for telemetry."""
    request_lower = user_request.lower()

    if any(kw in request_lower for kw in ["question", "quiz", "test", "mcq", "practice"]):
        return "test_generation"
    if any(kw in request_lower for kw in ["revision", "revise", "study plan", "schedule", "weak"]):
        return "revision_planning"
    if any(kw in request_lower for kw in ["mastery", "progress", "how am i", "weak topic"]):
        return "mastery_query"
    if any(kw in request_lower for kw in ["explain", "what is", "define", "how does", "why"]):
        return "question_answering"
    if any(kw in request_lower for kw in ["summarize", "summary", "overview", "key points"]):
        return "summarization"
    return "general"