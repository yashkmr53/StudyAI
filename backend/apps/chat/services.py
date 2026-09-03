"""Chatbot service (architecture §16, §57, Phase 1 Agentic AI).

User question → scoped hybrid retrieval → evidence-grounded answer via
the LLM provider (mock) → citation verification → persist messages.
Retrieval scoping guarantees the chatbot never sees another profile's
content.

Agent mode (Phase 1): When X-Agent-Mode header is present or AGENT_ENABLED,
uses StudyAIAgent for multi-step tool-use orchestration.
"""
import json
import logging
import re
import time
from collections.abc import Iterator

from django.conf import settings
from django.db import transaction

from apps.ai_classroom.services import EvidenceVerifier
from apps.chat.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

CHAT_PROMPT_VERSION = "chat:v1"
AGENT_PROMPT_VERSION = getattr(settings, "AGENT_PROMPT_VERSION", "agent_orchestrator:v1")

# Event types emitted over SSE during streaming chat.
EVT_TITLE = "title"
EVT_TOKEN = "token"
EVT_CITATIONS = "citations"
EVT_DONE = "done"
EVT_ERROR = "error"


def _sse(event: str, data: dict) -> str:
    """Encode a single Server-Sent Event payload."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _tokenize(text: str) -> Iterator[str]:
    """Split a generated answer into streaming-friendly chunks (word-by-word
    with trailing whitespace). Falls back to single chunk when text is
    short or already partially tokenized."""
    if not text:
        return iter([])
    # Split on word boundaries but keep the trailing whitespace so the
    # chunk reads naturally when concatenated by the client.
    parts = re.findall(r"\S+\s*", text)
    if not parts:
        return iter([text])
    return iter(parts)


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

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    @staticmethod
    def stream(
        session: ChatSession,
        content: str,
        *,
        use_agent: bool = False,
    ) -> Iterator[str]:
        """Generator that yields Server-Sent Events for a chat turn.

        Event sequence:
          - title (once, when a thread title is generated for a new thread)
          - token (multiple, streaming the assistant answer)
          - citations (once, when citations are available)
          - done (terminal, includes the persisted assistant message id)
          - error (terminal, on failure)

        The user message and any auto-generated title are committed before
        streaming begins so that sidebar updates are observable without a
        page refresh. The assistant message is persisted atomically at the
        end of the stream.
        """
        from apps.ai_classroom.budget import assert_within_budget

        content = (content or "").strip()
        if not content:
            yield _sse(EVT_ERROR, {"message": "Message content is required."})
            return

        try:
            assert_within_budget(session.profile_id)
        except Exception as exc:  # noqa: BLE001
            yield _sse(EVT_ERROR, {"message": str(exc) or "Budget exceeded."})
            return

        previous_messages = list(
            ChatMessage.objects.filter(session=session)
            .order_by("-created_at")[:20]
            .values("role", "content")
        )
        previous_messages = list(reversed(previous_messages))

        try:
            with transaction.atomic():
                ChatMessage.objects.create(
                    session=session, role=ChatMessage.Role.USER, content=content
                )
                generated_title: str | None = None
                if not session.title and ChatMessage.objects.filter(session=session).count() <= 1:
                    session.title = ChatService._generate_title(content)
                    session.save(update_fields=["title"])
                    generated_title = session.title
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist user message / title")
            yield _sse(EVT_ERROR, {"message": f"Failed to persist message: {exc}"})
            return

        if generated_title:
            yield _sse(EVT_TITLE, {"title": generated_title, "session_id": str(session.pk)})

        # Run the graph in non-streaming mode but stream the answer text
        # by chunking the final answer through the wire. This works for
        # any LLM provider (mock/ollama/etc.) without requiring each
        # provider to expose token-level streaming.
        try:
            if use_agent and getattr(settings, "AGENT_ENABLED", True):
                final_state = ChatService._run_agent_for_stream(session, content)
            else:
                final_state = ChatService._run_classic_for_stream(
                    session, content, previous_messages
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat stream failed")
            yield _sse(EVT_ERROR, {"message": str(exc) or "Chat failed."})
            return

        answer = final_state.get("answer", "") or ""
        citations = final_state.get("citations", []) or []
        verification_status = final_state.get("verification_status", "not_verified")
        verification_score = final_state.get("verification_score")
        route = final_state.get("route")
        has_evidence = bool(
            final_state.get("selected_evidence")
            or final_state.get("retrieved_evidence")
            or final_state.get("web_evidence")
        )
        if route == "conversational" or not has_evidence:
            citations = []

        # Emit tokens with a small artificial delay so the UI shows a
        # genuine stream effect even with mock providers. The delay is
        # skipped for empty answers.
        token_delay_ms = int(getattr(settings, "CHAT_STREAM_TOKEN_DELAY_MS", 25))
        for chunk in _tokenize(answer):
            yield _sse(EVT_TOKEN, {"delta": chunk})
            if token_delay_ms > 0:
                time.sleep(token_delay_ms / 1000.0)

        if citations:
            yield _sse(EVT_CITATIONS, {"citations": citations})

        try:
            with transaction.atomic():
                persisted = ChatMessage.objects.create(
                    session=session,
                    role=ChatMessage.Role.ASSISTANT,
                    content=answer,
                    citations=citations,
                    model=final_state.get("model", getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")),
                    prompt_version=CHAT_PROMPT_VERSION,
                    verification_status=verification_status,
                    verification_score=verification_score,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist assistant message")
            yield _sse(EVT_ERROR, {"message": f"Failed to save answer: {exc}"})
            return

        yield _sse(
            EVT_DONE,
            {
                "message_id": str(persisted.pk),
                "verification_status": verification_status,
                "verification_score": verification_score,
                "model": persisted.model,
            },
        )

    @staticmethod
    def _run_classic_for_stream(
        session: ChatSession,
        content: str,
        previous_messages: list[dict],
    ) -> dict:
        from ai.langgraph.graphs.chat_graph import invoke_chat_graph
        from ai.langgraph.state.chat_state import ChatState

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
        return invoke_chat_graph(initial_state)

    @staticmethod
    def _run_agent_for_stream(session: ChatSession, content: str) -> dict:
        from apps.agents.services.agent import StudyAIAgent

        agent = StudyAIAgent()
        result = agent.process_request(content, session.profile.user, session)
        return {
            "answer": result.answer,
            "citations": result.citations,
            "verification_status": result.verification_status,
            "verification_score": result.verification_score,
            "model": getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
        }