"""Documents API (architecture §45–48, §60).

POST /api/v1/documents                        create document + page + upload target
GET  /api/v1/documents/{id}
GET  /api/v1/documents/{id}/pages
GET  /api/v1/documents/{id}/revisions
POST /api/v1/documents/{id}/revisions         finalize-upload OR user-edit revision
POST /api/v1/documents/{id}/retry-processing
POST /api/v1/documents/pages/{page_id}/finalize-upload   (explicit §46 step)
"""
from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from apps.documents.models import (
    DigitizedDocument,
    Document,
    DocumentPage,
    DocumentPageRevision,
)
from apps.documents.serializers import (
    DocumentCreateSerializer,
    DocumentPageRevisionSerializer,
    DocumentPageSerializer,
    DocumentSerializer,
    RevisionCreateSerializer,
    RetryProcessingSerializer,
)
from apps.ai_classroom.services import EnrichmentService
from apps.audit.services import audit as audit_event
from apps.documents.services import IngestionService
from apps.jobs.models import Job
from apps.jobs.services import cancel_job, dispatch_job
from apps.profiles.models import Profile
from shared.authorization.services import ProfileAuthorizationService
from shared.throttles import LiveScopedRateThrottle, AIBudgetThrottle
from shared.exceptions import ValidationError


class DocumentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer
    http_method_names = ["get", "post", "head", "options"]
    throttle_scope = "ai"

    def get_queryset(self):
        return Document.objects.filter(profile__user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.validated_data["profile"]
        ProfileAuthorizationService.ensure_profile_access(request.user, profile)
        if serializer.validated_data.get("subject"):
            ProfileAuthorizationService.ensure_subject_access(request.user, serializer.validated_data["subject"])

        from providers.registry import get_object_storage

        storage = get_object_storage()
        document, page = IngestionService.create_document(
            request.user,
            profile=profile,
            source=Document.Source.UPLOAD,
            source_type=serializer.validated_data["source_type"],
            subject=serializer.validated_data.get("subject"),
            filename=serializer.validated_data["filename"],
        )
        ext = ".jpg" if "jpeg" in (request.data.get("content_type") or "") else ".png"
        key = f"{profile.id}/{page.id}{ext}"
        page.image_ref = key
        page.save(update_fields=("image_ref",))
        upload_url = storage.create_upload_url(key,content_type="application/octet-stream",ttl_seconds=settings.SIGNED_URL_TTL_SECONDS,)
        audit_event(actor=request.user, action="document.created", resource_type="document",
                    resource_id=document.pk, request=request)
        return Response(
            {
                "document": DocumentSerializer(document).data,
                "page": DocumentPageSerializer(page).data,
                "upload": {"url": upload_url, "method": "PUT", "key": key},
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def pages(self, request, pk=None):
        document = self.get_object()
        pages = DocumentPage.objects.filter(document=document)
        return Response(DocumentPageSerializer(pages, many=True).data)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        document = self.get_object()
        qs = DocumentPageRevision.objects.filter(page__document=document).select_related("page")
        page_id = request.query_params.get("page")
        if page_id:
            qs = qs.filter(page_id=page_id)
        return Response(DocumentPageRevisionSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="revisions")
    def create_revision(self, request, pk=None):
        """Two modes: finalize-upload (no lines) or user-edited revision (with lines)."""
        document = self.get_object()
        serializer = RevisionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page_id = str(serializer.validated_data["page_id"])
        lines = serializer.validated_data.get("lines")

        if lines:
            revision = IngestionService.create_user_revision(request.user, str(document.pk), page_id, lines)
            return Response({"revision": DocumentPageRevisionSerializer(revision).data, "job": None}, status=200)

        result = IngestionService.finalize_upload(request.user, page_id)
        if str(result["revision"].page.document_id) != str(document.pk):
            raise ValidationError("Page does not belong to this document.")
        return Response(
            {
                "revision": DocumentPageRevisionSerializer(result["revision"]).data,
                "job": _job_payload(result["job"]),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="retry-processing")
    def retry_processing(self, request, pk=None):
        document = self.get_object()
        serializer = RetryProcessingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = IngestionService.get_owned_page(request.user, str(serializer.validated_data["page_id"]))
        if str(page.document_id) != str(document.pk):
            raise ValidationError("Page does not belong to this document.")
        revision = (
            DocumentPageRevision.objects.filter(page=page).order_by("-revision_number").first()
        )
        if revision is None:
            raise ValidationError("Page has no revision to retry.")
        job = Job.objects.filter(revision_id=revision.pk, job_type="ocr").order_by("-created_at").first()
        if job is None:
            raise ValidationError("No OCR job exists for this page.")
        if job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
            Job.objects.filter(pk=job.pk).update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
            job.refresh_from_db()
            dispatch_job(job)
            return Response({"job": _job_payload(job)}, status=status.HTTP_202_ACCEPTED)
        raise ValidationError(f"Job is {job.status}; only failed jobs can be retried.")

    @action(detail=True, methods=["post"], url_path="pdf")
    def request_pdf(self, request, pk=None):
        """§60: POST /documents/{id}/pdf — 200 existing artifact or 202 render job."""
        from apps.documents.note_space import NoteSpaceService

        result = NoteSpaceService.request_pdf(request.user, str(pk))
        if result["artifact"] is not None:
            return Response(
                {"digitized_document": DigitizedDocumentSerializer(result["artifact"]).data, "job": None},
                status=status.HTTP_200_OK,
            )
        with_job = result["job"]
        return Response({"digitized_document": None, "job": _job_payload(with_job)}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="enrich",
            throttle_classes=[AIBudgetThrottle])
    def enrich(self, request, pk=None):
        """§60: POST /documents/{id}/enrich — 200 existing / 202 enrich job."""
        result = EnrichmentService.enqueue_enrichment(request.user, str(pk))
        if result["note"] is not None:
            from apps.ai_classroom.views_serializers import EnrichedNoteSerializer

            return Response({"enriched_note": EnrichedNoteSerializer(result["note"]).data, "job": None}, status=200)
        return Response(
            {"enriched_note": None, "job": _job_payload(result["job"])},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="enrichment")
    def enrichment(self, request, pk=None):
        """§60: GET /documents/{id}/enrichment."""
        note = EnrichmentService.latest_note(request.user, str(pk))
        if note is None:
            from shared.exceptions import ResourceNotFound

            raise ResourceNotFound("No enrichment exists for this document yet.")
        from apps.ai_classroom.views_serializers import EnrichedNoteSerializer

        return Response(EnrichedNoteSerializer(note).data)

    @action(detail=True, methods=["post"], url_path="refresh-ai",
            throttle_classes=[AIBudgetThrottle])
    def refresh_ai(self, request, pk=None):
        """§60: POST /documents/{id}/refresh-ai — forces regeneration."""
        result = EnrichmentService.enqueue_enrichment(request.user, str(pk), force_refresh=True)
        return Response(
            {"enriched_note": None, "job": _job_payload(result["job"])},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="tags")
    def tags(self, request, pk=None):
        """§60: GET /documents/{id}/tags — stable tags linked to this document."""
        document = self.get_object()
        from apps.ai_classroom.models import DocumentTag

        links = DocumentTag.objects.filter(document=document).select_related("tag")
        return Response({"results": [
            {
                "id": str(l.tag.pk),
                "stable_key": l.tag.stable_key,
                "display_name": l.tag.display_name,
                "linked_at": l.created_at,
            }
            for l in links
        ]})


def _job_payload(job: Job) -> dict:
    return {
        "id": str(job.pk),
        "job_type": job.job_type,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "idempotency_key": job.idempotency_key,
        "created_at": job.created_at,
    }


class DigitizedDocumentSerializer(serializers.Serializer):
    id = serializers.CharField()
    document = serializers.CharField()
    revision_ids = serializers.ListField()
    pdf_ref = serializers.CharField()
    renderer_version = serializers.CharField()
    file_size = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()

    def to_representation(self, obj):
        from apps.documents.models import DigitizedDocument

        assert isinstance(obj, DigitizedDocument)
        return {
            "id": str(obj.pk),
            "document": str(obj.document_id),
            "revision_ids": [
                {"revision_id": r["revision_id"], "page_number": r["page_number"]} for r in obj.revision_ids
            ],
            "renderer_version": obj.renderer_version,
            "file_size": obj.file_size,
            "created_at": obj.created_at,
        }


class DigitizedDocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/v1/digitized-documents[?document={id}] (§60)."""

    queryset = DigitizedDocument.objects.all()
    serializer_class = DigitizedDocumentSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = DigitizedDocument.objects.filter(document__profile__user=self.request.user)
        document_id = self.request.query_params.get("document")
        if document_id:
            qs = qs.filter(document_id=document_id)
        return qs


class DigitizedDownloadView(APIView):
    """GET /api/v1/digitized-documents/{id}/download — authz then short-lived signed URL."""

    def get(self, request, pk):
        from apps.documents.note_space import NoteSpaceService
        from providers.registry import get_object_storage

        artifact = NoteSpaceService.get_owned_artifact(request.user, str(pk))
        if not get_object_storage().exists(artifact.pdf_ref):
            raise ResourceNotFound("PDF object is missing from storage.")
        payload = NoteSpaceService.signed_download_url(artifact)
        return Response(payload)


class PageDownloadView(APIView):
    """GET /api/v1/documents/pages/{page_id}/download — signed URL for a page scan."""

    def get(self, request, page_id):
        from providers.registry import get_object_storage

        page = DocumentPage.objects.select_related("document__profile").get(pk=page_id)
        if page.document.profile.user_id != request.user.pk:
            raise ResourceNotFound("Page not found.")
        if not page.image_ref:
            raise ResourceNotFound("Page has no image.")
        storage = get_object_storage()
        if not storage.exists(page.image_ref):
            raise ResourceNotFound("Page image is missing from storage.")
        url = storage.signed_download_url(page.image_ref, ttl_seconds=settings.SIGNED_URL_TTL_SECONDS)
        return Response({"url": url, "expires_in": settings.SIGNED_URL_TTL_SECONDS, "file_size": None})


class FinalizeUploadView(APIView):
    """Explicit §46 step: POST /api/v1/documents/pages/{page_id}/finalize-upload."""

    def post(self, request, page_id):
        result = IngestionService.finalize_upload(request.user, str(page_id))
        return Response(
            {
                "revision": DocumentPageRevisionSerializer(result["revision"]).data,
                "job": _job_payload(result["job"]),
                "job_created": result["job_created"],
            },
            status=status.HTTP_202_ACCEPTED,
        )


class JobSerializer(serializers.Serializer):
    id = serializers.CharField()
    job_type = serializers.CharField()
    resource_type = serializers.CharField()
    resource_id = serializers.CharField()
    status = serializers.CharField()
    attempt_count = serializers.IntegerField()
    last_error = serializers.CharField()
    created_at = serializers.DateTimeField()

    def to_representation(self, obj: Job):
        return {
            "id": str(obj.pk),
            "job_type": obj.job_type,
            "resource_type": obj.resource_type,
            "resource_id": obj.resource_id,
            "status": obj.status,
            "attempt_count": obj.attempt_count,
            "last_error": obj.last_error,
            "created_at": obj.created_at,
        }


class JobViewSet(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/v1/jobs/{id} — owner-scoped via the job's profile (§60)."""

    queryset = Job.objects.all()
    serializer_class = JobSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        profile_ids = Profile.objects.filter(user=self.request.user).values_list("id", flat=True)
        return Job.objects.filter(profile_id__in=profile_ids)


class CancelJobView(APIView):
    """POST /api/v1/jobs/{id}/cancel (§60)."""

    def post(self, request, pk):
        from apps.profiles.models import Profile

        profile_ids = list(Profile.objects.filter(user=request.user).values_list("id", flat=True))
        try:
            job = Job.objects.get(pk=pk, profile_id__in=profile_ids)
        except (Job.DoesNotExist, ValueError, TypeError):
            from shared.exceptions import ResourceNotFound

            raise ResourceNotFound("Job not found.")
        job = cancel_job(job)
        return Response({"id": str(job.pk), "status": job.status})
