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

        # Load conversation history BEFORE creating the user message
        # so the current message is not duplicated in the prompt.
        previous_messages = list(
            ChatMessage.objects.filter(session=session)
            .order_by("-created_at")[:20]
            .values("role", "content")
        )
        previous_messages = list(reversed(previous_messages))

        # Create user message
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=content)

        # Generate title from first message if this is a new thread
        if not session.title and ChatMessage.objects.filter(session=session).count() <= 1:
            session.title = ChatService._generate_title(content)
            session.save(update_fields=["title"])

        # Agent mode: use StudyAIAgent for multi-step orchestration
        if use_agent and getattr(settings, "AGENT_ENABLED", True):
            return ChatService._ask_agent(session, content)

        # Classic RAG mode (original implementation)
        return ChatService._ask_classic(session, content, previous_messages=previous_messages)

    @staticmethod
    def _generate_title(content: str) -> str:
        """Generate a thread title from the first user message."""
        # Use the first 50 chars of the message, truncated at word boundary
        content = content.strip()
        if len(content) <= 50:
            return content
        # Truncate at word boundary
        truncated = content[:50]
        last_space = truncated.rfind(" ")
        if last_space > 20:
            return truncated[:last_space]
        return truncated

    @staticmethod
    def _ask_classic(session: ChatSession, content: str, previous_messages: list[dict] | None = None) -> ChatMessage:
        """LangGraph-based RAG chatbot implementation."""
        from ai.langgraph.graphs.chat_graph import invoke_chat_graph
        from ai.langgraph.state.chat_state import ChatState

        if previous_messages is None:
            previous_messages = list(
                ChatMessage.objects.filter(session=session)
                .order_by("-created_at")[:20]
                .values("role", "content")
            )
            previous_messages = list(reversed(previous_messages))

        initial_state = ChatState(
            user_request=content,
            profile_id=str(session.profile_id),
            subject_id=str(session.subject_id) if session.subject_id else None,
            session_id=str(session.pk),
            route=None,
            messages=previous_messages,
            retrieved_evidence=[],
            web_evidence=[],
            selected_evidence=[],
            answer="",
            citations=[],
            cited_contents=[],
            verification_status="not_verified",
            verification_score=0.0,
            retry_count=0,
            errors=[],
            execution_metadata={},
            current_date=None,
        )

        final_state = invoke_chat_graph(initial_state)

        answer = final_state.get("answer", "")
        citations = final_state.get("citations", [])
        verification_status = final_state.get("verification_status", "not_verified")
        verification_score = final_state.get("verification_score")

        # Determine if citations should be shown:
        # Only show citations for RAG responses (material/general_knowledge routes)
        # where evidence was actually retrieved and used.
        route = final_state.get("route")
        has_evidence = bool(final_state.get("selected_evidence") or final_state.get("retrieved_evidence") or final_state.get("web_evidence"))

        # Conversational/date/time responses should never have citations
        if route == "conversational" or not has_evidence:
            citations = []

        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=answer,
            citations=citations,
            model=final_state.get("model", getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")),
            prompt_version=CHAT_PROMPT_VERSION,
            verification_status=verification_status,
            verification_score=verification_score,
        )
        logger.info("Chat %s answered with %s citation(s) [%s] (route=%s)", session.pk, len(citations), verification_status, route)
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
