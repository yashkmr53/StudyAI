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
    image = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)


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
    throttle_classes = [LiveScopedRateThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_throttles(self):
        if (
            self.request
            and self.request.method == "POST"
            and self.action in ("messages", "stream_message", "send_message")
        ):
            return [AIBudgetThrottle()]
        return [LiveScopedRateThrottle()]

    def get_queryset(self):
        qs = ChatSession.objects.filter(profile__user=self.request.user)
        profile = getattr(self.request, "profile", None)
        if profile:
            qs = qs.filter(profile=profile)
        return qs

    def perform_content_negotiation(self, request):
        if getattr(self, "action", None) == "stream_message":
            from rest_framework.renderers import JSONRenderer
            return (JSONRenderer(), "application/json")
        return super().perform_content_negotiation(request)

    def create(self, request, *args, **kwargs):
        serializer = CreateSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = getattr(request, "profile", None)
        if not profile:
            from shared.exceptions import ValidationError

            raise ValidationError("No active profile found for this user.")

        subject = None
        if serializer.validated_data.get("subject"):
            try:
                subject = Subject.objects.get(
                    pk=serializer.validated_data["subject"], profile=profile
                )
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this profile.")
        session = ChatSession.objects.create(
            profile=profile,
            subject=subject,
            title=serializer.validated_data.get("title", ""),
        )
        return Response(ChatSessionSerializer(session).data, status=201)

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def messages(self, request, pk=None):
        session = self.get_object()
        if request.method == "POST":
            serializer = MessageInSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            # Check for agent mode header
            use_agent = request.headers.get("X-Agent-Mode", "").lower() == "true"
            content = serializer.validated_data["content"]
            image = serializer.validated_data.get("image")
            message = ChatService.ask(session, content, image=image, use_agent=use_agent)
            return Response(ChatMessageSerializer(message).data, status=201)
        messages = ChatMessage.objects.filter(session=session)
        return Response(ChatMessageSerializer(messages, many=True).data)

    @action(detail=True, methods=["post"], url_path="messages/stream")
    def stream_message(self, request, pk=None):
        """Stream the assistant answer for a user message via SSE.

        Emits: `title`, `token` (multiple), `citations`, `done`, `error`.
        """
        from django.http import StreamingHttpResponse
        from apps.accounts.services.budget import BudgetService, active_reservation_context

        session = self.get_object()
        serializer = MessageInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_agent = request.headers.get("X-Agent-Mode", "").lower() == "true"
        content = serializer.validated_data["content"]
        image = serializer.validated_data.get("image")

        raw_request = getattr(request, "_request", request)
        reservation = getattr(raw_request, "_budget_reservation", None)
        if reservation is not None:
            raw_request._budget_reservation_deferred = True

        def _budget_guarded_stream():
            res_id = reservation.reservation_id if reservation else None
            stream_errored = False
            with active_reservation_context(res_id):
                try:
                    for chunk in ChatService.stream(session, content, image=image, use_agent=use_agent):
                        if chunk.startswith("event: error"):
                            stream_errored = True
                        yield chunk
                except Exception:
                    stream_errored = True
                    raise
                finally:
                    if reservation is not None:
                        if stream_errored:
                            BudgetService.release(reservation)
                        else:
                            BudgetService.settle_from_logs(reservation)

        response = StreamingHttpResponse(
            _budget_guarded_stream(),
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
        content = serializer.validated_data["content"]
        image = serializer.validated_data.get("image")
        message = ChatService.ask(session, content, image=image, use_agent=use_agent)
        return Response(ChatMessageSerializer(message).data, status=201)