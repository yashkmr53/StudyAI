"""Agent API Views (Phase 1).

Endpoints for agentic chat and tool discovery.
"""
import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.agents.models import AgentExecutionLog
from apps.agents.serializers import (
    AgentChatRequestSerializer,
    AgentChatResponseSerializer,
    ToolMetadataSerializer,
    AgentExecutionLogSerializer,
)
from apps.agents.services.agent import StudyAIAgent
from apps.chat.models import ChatSession
from apps.profiles.models import Profile
from shared.throttles import AIBudgetThrottle

logger = logging.getLogger(__name__)


class AgentRateThrottle(UserRateThrottle):
    scope = "agent"
    rate = "30/minute"


class AgentViewSet(viewsets.GenericViewSet):
    throttle_classes = [AgentRateThrottle, AIBudgetThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return AgentExecutionLog.objects.filter(profile__user=self.request.user)

    @action(detail=False, methods=["post"], url_path="chat")
    def chat(self, request):
        """Process a user message through the StudyAI Agent."""
        serializer = AgentChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data["session_id"]
        content = serializer.validated_data["content"]

        try:
            session = ChatSession.objects.select_related("profile").get(
                pk=session_id, profile__user=request.user
            )
        except (ChatSession.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check budget
        from apps.ai_classroom.budget import assert_within_budget
        assert_within_budget(session.profile_id)

        # Create user message
        user_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.USER,
            content=content,
        )

        # Process through agent
        agent = StudyAIAgent()
        result = agent.process_request(content, request.user, session)

        # Persist assistant message with tool calls trace
        assistant_message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=result.answer,
            citations=result.citations + [{
                "verification_status": result.verification_status,
                "verification_score": result.verification_score,
            }] if result.verification_status else result.citations,
            model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
            prompt_version=getattr(settings, "AGENT_PROMPT_VERSION", "agent_orchestrator:v1"),
        )

        # Store tool calls in citations field for now (can be separate field later)
        # We'll include tool_calls in the response

        response_data = {
            "user": {
                "id": str(user_message.pk),
                "role": "user",
                "content": user_message.content,
                "citations": [],
                "created_at": user_message.created_at.isoformat(),
            },
            "assistant": {
                "id": str(assistant_message.pk),
                "role": "assistant",
                "content": assistant_message.content,
                "citations": assistant_message.citations,
                "tool_calls": [
                    {
                        "tool": tc.tool,
                        "arguments": tc.arguments,
                        "result": tc.result,
                        "latency_ms": tc.latency_ms,
                        "success": tc.success,
                        "error": tc.error,
                    }
                    for tc in result.tool_calls
                ],
                "trace_id": result.trace_id,
                "iterations": result.iterations,
                "total_tokens": result.total_tokens,
                "total_latency_ms": result.total_latency_ms,
                "outcome": result.outcome,
                "verification_status": result.verification_status,
                "verification_score": result.verification_score,
                "created_at": assistant_message.created_at.isoformat(),
            },
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="tools")
    def list_tools(self, request):
        """List all available agent tools with schemas."""
        from apps.agents.tools import get_tool_registry

        registry = get_tool_registry()
        tools = registry.list_tools()

        data = [
            {
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "category": tool.metadata.category,
                "input_schema": tool.metadata.input_schema.model_json_schema(),
                "output_schema": tool.metadata.output_schema.model_json_schema(),
                "requires_auth": tool.metadata.requires_auth,
                "timeout_seconds": tool.metadata.timeout_seconds,
            }
            for tool in tools
        ]

        return Response(data)

    @action(detail=False, methods=["get"], url_path="executions/(?P<request_id>[^/.]+)")
    def execution_trace(self, request, request_id=None):
        """Get execution trace for a specific agent request."""
        try:
            log = AgentExecutionLog.objects.get(request_id=request_id, profile__user=request.user)
        except AgentExecutionLog.DoesNotExist:
            return Response({"detail": "Execution trace not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AgentExecutionLogSerializer(log)
        return Response(serializer.data)


# Also add agent mode to existing chat endpoint
def patch_chat_service():
    """Monkey-patch ChatService to support agent mode via header."""
    from apps.chat.services import ChatService
    from apps.agents.services.agent import StudyAIAgent
    from apps.chat.models import ChatMessage
    from django.conf import settings

    original_ask = ChatService.ask

    @staticmethod
    @transaction.atomic
    def ask_with_agent(session: ChatSession, content: str, *, use_agent: bool = False) -> ChatMessage:
        if use_agent and getattr(settings, "AGENT_ENABLED", True):
            agent = StudyAIAgent()
            result = agent.process_request(content, session.profile.user, session)

            user_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.USER,
                content=content,
            )

            assistant_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.Role.ASSISTANT,
                content=result.answer,
                citations=result.citations,
                model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
                prompt_version=getattr(settings, "AGENT_PROMPT_VERSION", "agent_orchestrator:v1"),
            )
            return assistant_message

        return original_ask(session, content)

    ChatService.ask = ask_with_agent