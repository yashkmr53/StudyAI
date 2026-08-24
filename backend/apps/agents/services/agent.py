"""StudyAI Agent High-Level Interface (Phase 1).

Main entry point for agentic chat interactions.
"""
import uuid
import logging

from django.conf import settings
from django.db import transaction

from apps.chat.models import ChatMessage, ChatSession
from apps.profiles.models import Profile

from ai.langgraph.graphs.agent_graph import invoke_agent_graph
from ai.langgraph.state.agent_state import AgentState
from apps.agents.services.telemetry import record_agent_execution, classify_intent
from apps.agents.services.orchestrator import AgentResult, ToolCallRecord

logger = logging.getLogger(__name__)


class StudyAIAgent:
    """High-level agent interface for chat integration."""

    def __init__(self):
        pass

    def process_request(
        self,
        user_request: str,
        user,
        session: ChatSession,
    ) -> AgentResult:
        """Process a user request through the LangGraph agent orchestration loop."""
        request_id = f"agent:{session.pk}:{uuid.uuid4().hex[:8]}"

        from apps.ai_classroom.budget import assert_within_budget
        profile = Profile.objects.get(user=user)
        assert_within_budget(profile.pk)

        initial_state = AgentState(
            user_request=user_request,
            profile_id=str(profile.pk),
            subject_id=str(session.subject_id) if session.subject_id else None,
            session_id=str(session.pk),
            retrieved_evidence=[],
            selected_evidence=[],
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            tool_calls=[],
            iterations=0,
            max_iterations=getattr(settings, "AGENT_MAX_ITERATIONS", 5),
            max_tool_calls=getattr(settings, "AGENT_MAX_TOOL_CALLS", 10),
            errors=[],
            execution_metadata={},
        )

        final_state = invoke_agent_graph(initial_state)

        tool_calls = []
        for tc in final_state.get("tool_calls", []):
            tool_calls.append(ToolCallRecord(
                tool=tc.get("tool", ""),
                arguments=tc.get("arguments", {}),
                result=tc.get("result", {}),
                latency_ms=tc.get("latency_ms", 0),
                success=tc.get("success", False),
                error=tc.get("error"),
            ))

        result = AgentResult(
            answer=final_state.get("answer", ""),
            citations=final_state.get("citations", []),
            tool_calls=tool_calls,
            iterations=final_state.get("iterations", 0),
            total_tokens=0,
            total_latency_ms=0,
            outcome="success",
            trace_id=request_id,
            verification_status=final_state.get("verification_status"),
            verification_score=final_state.get("verification_score"),
        )

        record_agent_execution(
            request_id=request_id,
            profile=profile,
            intent_category=classify_intent(user_request),
            model_provider=getattr(settings, "LLM_PROVIDER", "unknown"),
            model_name=getattr(settings, "LLM_MODEL", "unknown"),
            prompt_version=getattr(settings, "AGENT_PROMPT_VERSION", "agent_orchestrator:v1"),
            tool_calls=[tc.__dict__ for tc in result.tool_calls],
            iterations=result.iterations,
            retrieved_evidence_ids=result.citations,
            total_tokens=result.total_tokens,
            total_latency_ms=result.total_latency_ms,
            outcome=result.outcome,
            citation_verification_status=result.verification_status,
            citation_verification_score=result.verification_score,
        )

        return result
