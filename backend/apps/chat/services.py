"""Chatbot service (architecture §16, §57, Phase 1 Agentic AI).

User question → scoped hybrid retrieval → evidence-grounded answer via
the LLM provider (mock) → citation verification → persist messages.
Retrieval scoping guarantees the chatbot never sees another profile's
content.

Agent mode (Phase 1): When X-Agent-Mode header is present or AGENT_ENABLED,
uses StudyAIAgent for multi-step tool-use orchestration.
"""
import logging

from django.conf import settings
from django.db import transaction

from apps.ai_classroom.services import EvidenceVerifier
from apps.chat.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

CHAT_PROMPT_VERSION = "chat:v1"
AGENT_PROMPT_VERSION = getattr(settings, "AGENT_PROMPT_VERSION", "agent_orchestrator:v1")


class ChatService:
    @staticmethod
    @transaction.atomic
    def ask(session: ChatSession, content: str, *, use_agent: bool = False) -> ChatMessage:
        content = (content or "").strip()
        if not content:
            from shared.exceptions import ValidationError

            raise ValidationError("Message content is required.")

        from apps.ai_classroom.budget import assert_within_budget

        assert_within_budget(session.profile_id)
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=content)

        # Agent mode: use StudyAIAgent for multi-step orchestration
        if use_agent and getattr(settings, "AGENT_ENABLED", True):
            return ChatService._ask_agent(session, content)

        # Classic RAG mode (original implementation)
        return ChatService._ask_classic(session, content)

    @staticmethod
    def _ask_classic(session: ChatSession, content: str) -> ChatMessage:
        """LangGraph-based RAG chatbot implementation."""
        from ai.langgraph.graphs.chat_graph import invoke_chat_graph
        from ai.langgraph.state.chat_state import ChatState

        initial_state = ChatState(
            user_request=content,
            profile_id=str(session.profile_id),
            subject_id=str(session.subject_id) if session.subject_id else None,
            session_id=str(session.pk),
            retrieved_evidence=[],
            selected_evidence=[],
            answer="",
            citations=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
        )

        final_state = invoke_chat_graph(initial_state)

        answer = final_state.get("answer", "")
        citations = final_state.get("citations", [])
        verification_status = final_state.get("verification_status", "not_verified")
        verification_score = final_state.get("verification_score")

        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=answer,
            citations=citations + [{"verification_status": verification_status, "verification_score": verification_score,
                                     "verifier_version": EvidenceVerifier.VERSION}],
            model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
            prompt_version=CHAT_PROMPT_VERSION,
        )
        logger.info("Chat %s answered with %s citation(s) [%s]", session.pk, len(citations), verification_status)
        return message

    @staticmethod
    def _ask_agent(session: ChatSession, content: str) -> ChatMessage:
        """Agentic mode using StudyAIAgent."""
        from apps.agents.services.agent import StudyAIAgent

        agent = StudyAIAgent()
        result = agent.process_request(content, session.profile.user, session)

        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=result.answer,
            citations=result.citations,
            model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
            prompt_version=AGENT_PROMPT_VERSION,
        )
        logger.info(
            "Agent chat %s answered with %s citation(s) [%s] (tools=%d, iterations=%d, outcome=%s)",
            session.pk, len(result.citations), result.verification_status,
            len(result.tool_calls), result.iterations, result.outcome
        )
        return message
