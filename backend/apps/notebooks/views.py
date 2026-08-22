"""Notebooks API (architecture §60 CRUD).

POST   /api/v1/notebooks                    create notebook
GET    /api/v1/notebooks                    list notebooks
GET    /api/v1/notebooks/{id}               retrieve notebook
PATCH  /api/v1/notebooks/{id}               update notebook (title, description, cover)
DELETE /api/v1/notebooks/{id}               delete notebook
POST   /api/v1/notebooks/{id}/pages         add page
GET    /api/v1/notebooks/{id}/pages         list pages
PATCH  /api/v1/notebooks/{id}/pages/{page_id}  update page canvas state
DELETE /api/v1/notebooks/{id}/pages/{page_id}  delete page
POST   /api/v1/notebooks/{id}/pages/{page_id}/lines  append strokes
GET    /api/v1/notebooks/{id}/pages/{page_id}/lines  list lines
"""
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notebooks.models import Notebook, NotebookPage, NotebookLine
from apps.notebooks.serializers import (
    NotebookSerializer,
    NotebookCreateSerializer,
    NotebookPageSerializer,
    NotebookLineSerializer,
    NotebookPageCreateSerializer,
    NotebookPageUpdateSerializer,
)
from apps.profiles.models import Profile
from shared.authorization.services import ProfileAuthorizationService
from shared.throttles import LiveScopedRateThrottle
from shared.exceptions import ValidationError, ResourceNotFound


class NotebookViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotebookSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    throttle_scope = "ai"

    def get_queryset(self):
        return Notebook.objects.filter(profile__user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return NotebookCreateSerializer
        return NotebookSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.validated_data["profile"]
        ProfileAuthorizationService.ensure_profile_access(request.user, profile)
        if serializer.validated_data.get("subject"):
            ProfileAuthorizationService.ensure_subject_access(request.user, serializer.validated_data["subject"])

        notebook = Notebook.objects.create(
            profile=profile,
            subject=serializer.validated_data.get("subject"),
            title=serializer.validated_data["title"],
            description=serializer.validated_data.get("description", ""),
        )
        return Response(NotebookSerializer(notebook).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = NotebookSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotebookPageViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotebookPageSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        notebook_pk = self.kwargs.get("notebook_pk")
        return NotebookPage.objects.filter(notebook_id=notebook_pk, notebook__profile__user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return NotebookPageCreateSerializer
        if self.action in ("update", "partial_update"):
            return NotebookPageUpdateSerializer
        return NotebookPageSerializer

    def create(self, request, *args, **kwargs):
        notebook_pk = self.kwargs.get("notebook_pk")
        notebook = Notebook.objects.filter(pk=notebook_pk, profile__user=request.user).first()
        if not notebook:
            raise ResourceNotFound("Notebook not found.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["notebook"].pk != notebook.pk:
            raise ValidationError("Page notebook does not match.")

        page = NotebookPage.objects.create(
            notebook=notebook,
            page_number=serializer.validated_data["page_number"],
            canvas_state=serializer.validated_data.get("canvas_state", {}),
        )
        return Response(NotebookPageSerializer(page).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def lines(self, request, notebook_pk=None, pk=None):
        page = self.get_object()

        if request.method == "GET":
            lines = NotebookLine.objects.filter(page=page)
            return Response(NotebookLineSerializer(lines, many=True).data)

        # POST: append strokes
        serializer = NotebookLineSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        created_lines = []
        current_max = NotebookLine.objects.filter(page=page).count()
        for i, line_data in enumerate(serializer.validated_data):
            line = NotebookLine.objects.create(
                page=page,
                line_index=current_max + i,
                points=line_data["points"],
                color=line_data.get("color", "#000000"),
                width=line_data.get("width", 2.0),
                tool=line_data.get("tool", "pen"),
            )
            created_lines.append(line)

        return Response(NotebookLineSerializer(created_lines, many=True).data, status=status.HTTP_201_CREATED)