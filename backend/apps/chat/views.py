"""Chat endpoints (architecture §16/§57, §60)."""
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.chat.models import ChatMessage, ChatSession
from apps.chat.services import ChatService
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from shared.throttles import LiveScopedRateThrottle, AIBudgetThrottle


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ("id", "subject", "title", "created_at")


class CreateSessionSerializer(serializers.Serializer):
    subject = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)


class MessageInSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=4000)


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ("id", "role", "content", "citations", "model", "prompt_version", "created_at")


class ChatSessionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChatSessionSerializer
    throttle_scope = "ai"
    throttle_classes = [AIBudgetThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return ChatSession.objects.filter(profile__user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = CreateSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = None
        if serializer.validated_data.get("subject"):
            try:
                subject = Subject.objects.get(
                    pk=serializer.validated_data["subject"], profile__user=request.user
                )
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this user.")
        session = ChatSession.objects.create(
            profile=Profile.objects.filter(user=request.user).first(),
            subject=subject,
            title=serializer.validated_data.get("title", ""),
        )
        return Response(ChatSessionSerializer(session).data, status=201)

    @action(detail=True, methods=["get", "post"], url_path="messages",
            throttle_classes=[AIBudgetThrottle])
    def messages(self, request, pk=None):
        session = self.get_object()
        if request.method == "POST":
            serializer = MessageInSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            # Check for agent mode header
            use_agent = request.headers.get("X-Agent-Mode", "").lower() == "true"
            message = ChatService.ask(session, serializer.validated_data["content"], use_agent=use_agent)
            return Response(ChatMessageSerializer(message).data, status=201)
        messages = ChatMessage.objects.filter(session=session)
        return Response(ChatMessageSerializer(messages, many=True).data)

    @action(detail=True, methods=["post"], url_path="messages/stream",
            throttle_classes=[AIBudgetThrottle])
    def stream_message(self, request, pk=None):
        """Stream the assistant answer for a user message via SSE.

        Emits: `title`, `token` (multiple), `citations`, `done`, `error`.
        """
        from django.http import StreamingHttpResponse

        session = self.get_object()
        serializer = MessageInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_agent = request.headers.get("X-Agent-Mode", "").lower() == "true"
        content = serializer.validated_data["content"]

        response = StreamingHttpResponse(
            ChatService.stream(session, content, use_agent=use_agent),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache, no-transform"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response

    def send_message(self, request, pk=None):
        session = self.get_object()
        serializer = MessageInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_agent = request.headers.get("X-Agent-Mode", "").lower() == "true"
        message = ChatService.ask(session, serializer.validated_data["content"], use_agent=use_agent)
        return Response(ChatMessageSerializer(message).data, status=201)