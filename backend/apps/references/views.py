"""Reference Library API views (Phase 11 §12).

Provides upload, listing, status polling, and deletion endpoints for
ReferenceDocument and ReferenceChunk entities.
"""
import logging
import uuid
from pathlib import Path

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.references.models import ReferenceChunk, ReferenceDocument
from apps.references.serializers import (
    ReferenceChunkSerializer,
    ReferenceDocumentSerializer,
    ReferenceUploadSerializer,
)
from apps.references.tasks import enqueue_reference_ingestion
from apps.subjects.models import Subject
from providers.registry import get_object_storage
from shared.authorization.services import ProfileAuthorizationService

logger = logging.getLogger(__name__)


class ReferenceDocumentViewSet(viewsets.ModelViewSet):
    """API for managing reference library documents."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ReferenceDocumentSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        # Allow viewing global references + references belonging to user's profiles
        qs = ReferenceDocument.objects.filter(
            Q(profile__user=user) | Q(profile__isnull=True)
        )

        # Optional profile filter
        active_profile = ProfileAuthorizationService.get_active_profile(self.request)
        profile_param = self.request.query_params.get("profile")
        if profile_param:
            qs = qs.filter(Q(profile_id=profile_param) | Q(profile__isnull=True))
        elif active_profile:
            qs = qs.filter(Q(profile=active_profile) | Q(profile__isnull=True))

        # Optional subject filter
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            qs = qs.filter(Q(subject_id=subject_id) | Q(subject__isnull=True))

        return qs.select_related("subject", "profile")

    def create(self, request, *args, **kwargs):
        """Upload a new reference PDF and trigger automatic background indexing."""
        serializer = ReferenceUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        title = serializer.validated_data.get("title")
        if not title:
            # Fallback to file name without extension
            title = Path(uploaded_file.name).stem.replace("_", " ").title()

        source_type = serializer.validated_data.get("source_type", ReferenceDocument.SourceType.TEXTBOOK)
        subject_id = serializer.validated_data.get("subject_id")
        is_global = serializer.validated_data.get("is_global", False)

        subject = None
        if subject_id:
            try:
                subject = Subject.objects.get(pk=subject_id)
            except Subject.DoesNotExist:
                return Response({"detail": "Subject not found"}, status=status.HTTP_404_NOT_FOUND)

        active_profile = ProfileAuthorizationService.get_active_profile(request)
        # Determine profile: if is_global requested and user is staff/allowed, profile is None
        profile = None if is_global else active_profile

        ref_id = uuid.uuid4()
        storage_key = f"references/{ref_id}/{uploaded_file.name}"

        # Store in object storage (MinIO or local)
        try:
            storage = get_object_storage()
            storage.store_bytes(storage_key, uploaded_file.read())
        except Exception as exc:
            logger.exception("Failed to store reference file: %s", exc)
            return Response(
                {"detail": f"Failed to store file in object storage: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        ref_doc = ReferenceDocument.objects.create(
            id=ref_id,
            title=title,
            source_type=source_type,
            file_path=storage_key,
            subject=subject,
            profile=profile,
            status=ReferenceDocument.Status.PENDING,
            metadata={"filename": uploaded_file.name, "file_size": uploaded_file.size},
        )

        # Automatically enqueue ingestion task
        enqueue_reference_ingestion(ref_doc)

        out_serializer = self.get_serializer(ref_doc)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Delete reference document, cleaning up storage, chunks, and embeddings."""
        instance = self.get_object()

        # Authorization: user must own the profile or be staff for global docs
        if instance.profile and instance.profile.user_id != request.user.pk:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        active_profile = ProfileAuthorizationService.get_active_profile(request)
        if instance.profile and active_profile and instance.profile_id != active_profile.pk:
            return Response({"detail": "Forbidden: Cannot delete reference belonging to another profile"}, status=status.HTTP_403_FORBIDDEN)
        if not instance.profile and not request.user.is_staff:
            return Response({"detail": "Only staff members can delete global reference documents."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Clean up storage file
        if instance.file_path:
            try:
                storage = get_object_storage()
                if storage.exists(instance.file_path):
                    storage.delete(instance.file_path)
            except Exception as exc:
                logger.warning("Failed to delete storage file %s: %s", instance.file_path, exc)

        # 2. ReferenceChunks and embeddings delete via CASCADE
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        """Get live processing status and statistics."""
        instance = self.get_object()
        return Response({
            "id": str(instance.pk),
            "title": instance.title,
            "status": instance.status,
            "page_count": instance.page_count,
            "chunk_count": instance.chunk_count,
            "error_message": instance.error_message,
            "updated_at": instance.updated_at,
        })

    @action(detail=True, methods=["get"])
    def chunks(self, request, pk=None):
        """List chunks for this reference document."""
        instance = self.get_object()
        chunks = instance.chunks.order_by("chunk_index")[:100]
        serializer = ReferenceChunkSerializer(chunks, many=True)
        return Response(serializer.data)
