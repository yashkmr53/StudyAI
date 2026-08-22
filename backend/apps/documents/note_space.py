"""NoteSpace service (architecture §7, §49, §60, §67).

- Layout extraction reads ONLY DocumentLine texts (+ explicit heading
  flags) of the document's current page revisions. Nothing is summarized,
  paraphrased, or corrected — faithful transcription in, typed PDF out.
- DigitizedDocument artifacts are immutable and content-addressed:
  same revisions + renderer version ⇒ same artifact; any source revision
  change ⇒ a NEW artifact (old ones retained).
"""
import hashlib
import json
import logging

from django.conf import settings
from django.db import transaction

from apps.documents.models import (
    DigitizedDocument,
    Document,
    DocumentPageRevision,
)
from apps.jobs.models import Job
from shared.exceptions import ResourceNotFound, ValidationError

logger = logging.getLogger(__name__)


def renderer_version() -> str:
    return getattr(settings, "RENDERER_VERSION", "notespace-pdf-v1")


def extract_layout(document: Document) -> list[dict]:
    """Faithful layout extraction: current revision lines per page, in order.

    Returns [{page_number, lines:[{text,is_heading}]}]. Raises if any page
    has no current revision (nothing to render yet).
    """
    pages = list(document.pages.order_by("page_number"))
    if not pages:
        raise ValidationError("Document has no pages to render.")
    layout = []
    for page in pages:
        if not page.current_revision_id:
            raise ValidationError(f"Page {page.page_number} has no completed revision.")
        revision = DocumentPageRevision.objects.get(pk=page.current_revision_id)
        lines = [
            {"text": line.text, "is_heading": bool(line.is_heading)}
            for line in revision.lines.order_by("line_index")
        ]
        layout.append({"page_number": page.page_number, "lines": lines})
    return layout


def compute_descriptor_hash(layout: list[dict]) -> tuple[str, list[dict]]:
    descriptor = {
        "renderer_version": renderer_version(),
        "pages": [
            {
                "page_number": p["page_number"],
                "revision_id": str(p["revision_id"]),
                "content_hash": p["content_hash"],
                "lines": p["lines"],
            }
            for p in layout
        ],
    }
    canonical = json.dumps(descriptor, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest(), descriptor["pages"]


class NoteSpaceService:
    @staticmethod
    def get_owned_document(user, document_id) -> Document:
        try:
            return Document.objects.get(pk=document_id, profile__user=user)
        except (Document.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Document not found.")

    @classmethod
    def build_layout_with_revisions(cls, document: Document) -> list[dict]:
        """extract_layout enriched with revision identity for hashing."""
        pages = list(document.pages.order_by("page_number"))
        if not pages:
            raise ValidationError("Document has no pages to render.")
        layout = []
        for page in pages:
            if not page.current_revision_id:
                raise ValidationError(f"Page {page.page_number} has no completed revision.")
            revision = DocumentPageRevision.objects.prefetch_related("lines").get(pk=page.current_revision_id)
            lines = [
                {"text": line.text, "is_heading": bool(line.is_heading)}
                for line in revision.lines.order_by("line_index")
            ]
            layout.append(
                {
                    "page_number": page.page_number,
                    "revision_id": str(revision.pk),
                    "content_hash": revision.content_hash,
                    "lines": lines,
                }
            )
        return layout

    @classmethod
    def request_pdf(cls, user, document_id) -> dict:
        """POST /documents/{id}/pdf handler.

        Returns existing artifact when revisions + renderer version are
        unchanged; otherwise enqueues an async render job → 202 semantics.
        """
        from apps.jobs.services import dispatch_job, get_or_create_job

        with transaction.atomic():
            document = cls.get_owned_document(user, document_id)
            layout = cls.build_layout_with_revisions(document)
            content_hash, _descriptor_pages = compute_descriptor_hash(layout)

            existing = DigitizedDocument.objects.filter(
                document=document, content_hash=content_hash
            ).first()
            if existing:
                return {"artifact": existing, "job": None, "created": False}

            job, created = get_or_create_job(
                job_type="pdf_render",
                resource_type="document",
                resource_id=str(document.pk),
                profile_id=document.profile_id,
                idempotency_key=f"pdf:{document.pk}:{content_hash[:32]}",
            )
            # carry layout through to the worker via module-level cache is
            # unsafe across processes; the worker re-derives layout instead.
            if created or job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
                if not created:
                    Job.objects.filter(pk=job.pk).update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
                    job.refresh_from_db()
                dispatch_job(job)

        return {"artifact": None, "job": job, "created": created}

    @staticmethod
    def render_and_store(job: Job) -> None:
        """Worker body for pdf_render jobs (runs under executor RLS scope)."""
        from providers.registry import get_object_storage
        from apps.documents.pdf_renderer import render_pdf

        document = Document.objects.get(pk=job.resource_id)
        layout = NoteSpaceService.build_layout_with_revisions(document)
        content_hash, pages = compute_descriptor_hash(layout)

        existing = DigitizedDocument.objects.filter(document=document, content_hash=content_hash).first()
        if existing:
            return  # rendered while we waited

        title = f"StudyAI Notes — {document.pk}"
        pdf_bytes = render_pdf(pages=pages, document_title=title)

        storage = get_object_storage()
        pdf_ref = f"{document.profile_id}/{document.pk}/{content_hash[:24]}.pdf"
        size = storage.store_bytes(pdf_ref, pdf_bytes)

        DigitizedDocument.objects.create(
            document=document,
            content_hash=content_hash,
            revision_ids=[{"revision_id": p["revision_id"], "page_number": p["page_number"]} for p in pages],
            pdf_ref=pdf_ref,
            renderer_version=renderer_version(),
            file_size=size,
        )
        logger.info(
            "Rendered PDF %s for document %s (%s bytes, %s pages)",
            pdf_ref, document.pk, size, len(pages),
        )

    @staticmethod
    def get_owned_artifact(user, digitized_id) -> DigitizedDocument:
        try:
            return DigitizedDocument.objects.get(pk=digitized_id, document__profile__user=user)
        except (DigitizedDocument.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Digitized document not found.")

    @staticmethod
    def signed_download_url(artifact: DigitizedDocument) -> dict:
        from providers.registry import get_object_storage

        url = get_object_storage().create_download_url(artifact.pdf_ref)
        return {
            "url": url,
            "expires_in": getattr(settings, "SIGNED_URL_TTL_SECONDS", 300),
            "file_size": artifact.file_size,
        }
