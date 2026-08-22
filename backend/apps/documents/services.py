"""Ingestion services (architecture §6, §45–48, §67).

- finalize_upload: object uploaded → validate → hash → DocumentPageRevision
  → logical OCR job (idempotency key §20) → 202 semantics.
- run_ocr_job: worker flow (§47) — idempotency check, primary/fallback OCR,
  atomic line persistence, review-status update. The original image is
  never overwritten.
- create_user_revision: user edits create a NEW immutable revision (§48).
"""
import hashlib
import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.jobs.models import Job
from shared.idempotency.keys import ocr_key
from shared.exceptions import ResourceNotFound, ValidationError

logger = logging.getLogger(__name__)


def _pipeline_version() -> str:
    return getattr(settings, "OCR_PIPELINE_VERSION", "mock-v1")


def _review_threshold() -> float:
    return float(getattr(settings, "OCR_REVIEW_THRESHOLD", 0.80))


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(snapshot: dict | list) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


class IngestionService:
    @staticmethod
    def get_owned_document(user, document_id) -> Document:
        try:
            return Document.objects.get(pk=document_id, profile__user=user)
        except (Document.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Document not found.")

    @staticmethod
    def get_owned_page(user, page_id) -> DocumentPage:
        try:
            return DocumentPage.objects.select_related("document").get(pk=page_id, document__profile__user=user)
        except (DocumentPage.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Document page not found.")

    @staticmethod
    def create_document(user, *, profile, source: str, source_type: str, subject=None, filename: str = "") -> tuple[Document, DocumentPage]:
        document = Document.objects.create(
            profile=profile,
            subject=subject,
            source=source,
            source_type=source_type,
        )
        page = DocumentPage.objects.create(document=document, page_number=1)
        return document, page

    @staticmethod
    def enqueue_ocr_job(page: DocumentPage, revision: DocumentPageRevision) -> tuple[Job, bool]:
        from apps.jobs.services import dispatch_job, get_or_create_job

        job, created = get_or_create_job(
            job_type="ocr",
            resource_type="document_page_revision",
            resource_id=str(revision.pk),
            profile_id=page.document.profile_id,
            revision_id=revision.pk,
            idempotency_key=ocr_key(page.pk, revision.content_hash, _pipeline_version()),
        )
        if created or job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
            if not created:
                # retry-processing path: requeue a failed job for the same content
                Job.objects.filter(pk=job.pk).update(
                    status=Job.Status.QUEUED, next_retry_at=None, last_error=""
                )
                job.refresh_from_db()
            dispatch_job(job)
        return job, created

    @classmethod
    def finalize_upload(cls, user, page_id) -> dict:
        """Object uploaded → validate → hash → revision → OCR job (§46)."""
        from providers.registry import get_object_storage

        storage = get_object_storage()
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id)
            if not page.image_ref or not storage.exists(page.image_ref):
                raise ValidationError("No uploaded object found for this page.")
            data = storage.read_bytes(page.image_ref)
            content_hash = compute_content_hash(data)

            revision = cls._create_revision_locked(
                page,
                content_hash=content_hash,
                ocr_status=DocumentPageRevision.OcrStatus.PENDING,
            )
            job, created = cls.enqueue_ocr_job(page, revision)

        # Eager dispatch may have finished the job before we respond; refresh
        # so callers never see stale pending state.
        revision.refresh_from_db()
        job.refresh_from_db()
        return {"revision": revision, "job": job, "job_created": created}

    @staticmethod
    def _create_revision_locked(page: DocumentPage, *, content_hash: str, ocr_status: str, edited_by=None, snapshot=None) -> DocumentPageRevision:
        last_number = (
            DocumentPageRevision.objects.filter(page=page)
            .order_by("-revision_number")
            .values_list("revision_number", flat=True)
            .first()
        )
        revision = DocumentPageRevision.objects.create(
            page=page,
            revision_number=(last_number or 0) + 1,
            content_hash=content_hash,
            content_snapshot=snapshot if snapshot is not None else {},
            edited_by=edited_by,
            ocr_status=ocr_status,
        )
        page.current_revision_id = revision.pk
        page.ocr_status = ocr_status
        page.needs_review = ocr_status == DocumentPageRevision.OcrStatus.NEEDS_REVIEW
        page.save(update_fields=("current_revision_id", "ocr_status", "needs_review"))
        return revision

    @classmethod
    def create_user_revision(cls, user, document_id, page_id, lines: list[dict]) -> DocumentPageRevision:
        """§48: user edits create a new immutable revision; the old one stays."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")
            clean_lines = []
            for i, line in enumerate(lines):
                text = (line.get("text") or "").strip()
                if not text:
                    raise ValidationError(f"Line {i} has no text.")
                clean_lines.append(
                    {
                        "line_index": i,
                        "text": text,
                        "bbox": line.get("bbox"),
                        "confidence": None,
                    }
                )
            if not clean_lines:
                raise ValidationError("At least one line is required.")
            snapshot = {"lines": clean_lines, "origin": "user_edit"}
            revision = cls._create_revision_locked(
                page,
                content_hash=snapshot_hash(snapshot),
                ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
                edited_by=user,
                snapshot=snapshot,
            )
            DocumentLine.objects.bulk_create(
                [
                    DocumentLine(
                        page_revision=revision,
                        line_index=l["line_index"],
                        text=l["text"],
                        bbox=l["bbox"],
                        confidence_score=None,
                    )
                    for l in clean_lines
                ]
            )
            # §10: content changed → document must be re-indexed.
            from apps.retrieval.services import enqueue_index_job

            enqueue_index_job(page.document)
            return revision


def run_ocr_job(job: Job) -> None:
    """Worker flow (§47). Runs inside the trusted RLS context established by the executor."""
    from providers.registry import get_object_storage, get_ocr_provider

    revision = DocumentPageRevision.objects.select_related("page", "page__document").get(pk=job.resource_id)
    page = revision.page

    # Idempotency inside the handler: completed revisions are not re-OCRed.
    if revision.ocr_status == DocumentPageRevision.OcrStatus.COMPLETED and revision.lines.exists():
        return

    storage = get_object_storage()
    if not page.image_ref or not storage.exists(page.image_ref):
        raise ValidationError("Image object missing for OCR.")

    DocumentPageRevision.objects.filter(pk=revision.pk).update(
        ocr_status=DocumentPageRevision.OcrStatus.PROCESSING
    )

    request_id = f"job_{job.pk}"
    chain = get_ocr_provider()
    result, attempted = chain.recognize(page.image_ref, request_id=request_id)

    lines = sorted(result.lines or [], key=lambda l: l.get("line_index", 0))
    avg_confidence = result.confidence
    needs_review = avg_confidence < _review_threshold()

    # One transaction: claim result + lines + status + downstream hook (§67).
    with transaction.atomic():
        revision.refresh_from_db()
        DocumentLine.objects.filter(page_revision=revision).delete()  # safe re-run
        DocumentLine.objects.bulk_create(
            [
                DocumentLine(
                    page_revision=revision,
                    line_index=i,
                    text=line["text"],
                    bbox=line.get("bbox"),
                    confidence_score=line.get("confidence"),
                )
                for i, line in enumerate(lines)
            ]
        )
        revision.content_snapshot = {"lines": lines, "attempted_providers": attempted}
        revision.ocr_provider = result.provider
        revision.ocr_status = (
            DocumentPageRevision.OcrStatus.NEEDS_REVIEW
            if needs_review
            else DocumentPageRevision.OcrStatus.COMPLETED
        )
        revision.save(update_fields=("content_snapshot", "ocr_provider", "ocr_status"))

        page.needs_review = needs_review
        page.ocr_status = revision.ocr_status
        page.save(update_fields=("needs_review", "ocr_status"))

    # §47 downstream enqueue (Phase 5): chunk + embed + index the document.
    from apps.retrieval.services import enqueue_index_job

    index_job, index_created = enqueue_index_job(page.document)
    logger.info(
        "OCR job %s completed via %s (%s lines, review=%s); index job %s",
        job.pk, attempted, len(lines), needs_review,
        "created" if index_created else f"reused({index_job.status})",
    )
