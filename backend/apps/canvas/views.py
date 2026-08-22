"""Canvas API (architecture §60).

POST /api/v1/canvas/sessions
GET  /api/v1/canvas/sessions[/{id}]
POST /api/v1/canvas/sessions/{id}/heartbeat
POST /api/v1/canvas/sessions/{id}/takeover
POST /api/v1/canvas/pages
POST /api/v1/canvas/pages/{id}/strokes
POST /api/v1/canvas/pages/{id}/finalize

Business logic lives in apps.canvas.services; views stay thin.
"""
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.canvas.models import CanvasPage, CanvasSession
from apps.canvas.serializers import (
    CanvasPageSerializer,
    CanvasSessionCreateSerializer,
    CanvasSessionSerializer,
    FinalizeSerializer,
    HeartbeatSerializer,
    StrokeBatchSerializer,
    TakeoverSerializer,
)
from apps.canvas.services import CanvasSessionService, CanvasSyncService
from shared.authorization.services import ProfileAuthorizationService


class CanvasSessionViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CanvasSessionSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return CanvasSession.objects.filter(profile__user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return CanvasSessionCreateSerializer
        return CanvasSessionSerializer

    def create(self, request, *args, **kwargs):
        serializer = CanvasSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.validated_data["profile"]
        ProfileAuthorizationService.ensure_profile_access(request.user, profile)
        session = CanvasSessionService.create_session(
            request.user,
            profile,
            device_id=serializer.validated_data["device_id"],
            subject=serializer.validated_data.get("subject"),
        )
        return Response(CanvasSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def heartbeat(self, request, pk=None):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = CanvasSessionService.heartbeat(
            request.user, pk,
            device_id=serializer.validated_data["device_id"],
            lock_generation=serializer.validated_data["lock_generation"],
        )
        return Response(CanvasSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def takeover(self, request, pk=None):
        serializer = TakeoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = CanvasSessionService.takeover(
            request.user, pk,
            device_id=serializer.validated_data["device_id"],
        )
        return Response(CanvasSessionSerializer(session).data)


class CanvasPageViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CanvasPageSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return CanvasPage.objects.filter(session__profile__user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = CanvasPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["session"].pk
        page_number = serializer.validated_data["page_number"]
        device_id = request.data.get("device_id")
        lock_generation = request.data.get("lock_generation")
        if not device_id or lock_generation is None:
            from shared.exceptions import ValidationError

            raise ValidationError("device_id and lock_generation are required.")
        try:
            lock_generation_int = int(lock_generation)
        except (TypeError, ValueError):
            from shared.exceptions import ValidationError

            raise ValidationError("lock_generation must be an integer.")
        page = CanvasSyncService.create_page(
            request.user, session_id, page_number, device_id=device_id, lock_generation=lock_generation_int
        )
        return Response(CanvasPageSerializer(page).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def strokes(self, request, pk=None):
        serializer = StrokeBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = CanvasSyncService.append_strokes(
            request.user, pk,
            device_id=serializer.validated_data["device_id"],
            lock_generation=serializer.validated_data["lock_generation"],
            strokes=serializer.validated_data["strokes"],
        )
        return Response(result)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        serializer = FinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = CanvasSyncService.finalize_page(
            request.user, pk,
            device_id=serializer.validated_data["device_id"],
            lock_generation=serializer.validated_data["lock_generation"],
        )
        return Response(result)
