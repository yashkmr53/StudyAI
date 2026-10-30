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
import uuid
from typing import Optional, Union

from django.conf import settings
from django.db import transaction
from django.utils import timezone
try:
    from celery.exceptions import SoftTimeLimitExceeded
except ImportError:
    class SoftTimeLimitExceeded(Exception):
        pass

from apps.documents.models import Document, DocumentLine, DocumentPage, DocumentPageRevision
from apps.jobs.models import Job
from shared.idempotency.keys import ocr_key
from shared.exceptions import ResourceNotFound, RevisionConflict, ValidationError

logger = logging.getLogger(__name__)


def _pipeline_version() -> str:
    return getattr(settings, "OCR_PIPELINE_VERSION", "mock-v1")


def _review_threshold() -> float:
    return float(getattr(settings, "OCR_REVIEW_THRESHOLD", 0.80))


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(snapshot: Union[dict, list]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def sync_page_approval_and_indexing(document: Document, page: DocumentPage) -> None:
    """Single authoritative helper called on approval, user revision, reopen, ignore, unignore."""
    from apps.ai_classroom.services import _descriptor
    from apps.ai_classroom.models import EnrichedNote
    from apps.retrieval.services import enqueue_page_index_job
    from apps.retrieval.models import NoteChunk

    new_hash = _descriptor(document)
    EnrichedNote.objects.filter(document=document, superseded=False).exclude(content_hash=new_hash).update(ai_stale=True)

    if page.is_approved and not page.is_ignored:
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            enqueue_page_index_job(page)
        else:
            transaction.on_commit(lambda: enqueue_page_index_job(page))
    else:
        NoteChunk.objects.filter(
            document=document,
            page_start__lte=page.page_number,
            page_end__gte=page.page_number,
            stale=False,
        ).update(stale=True)
        DocumentPage.objects.filter(pk=page.pk).update(indexed_text_hash="")
        page.indexed_text_hash = ""


class IngestionService:
    @staticmethod
    def get_owned_document(user, document_id) -> Document:
        try:
            return Document.objects.get(pk=document_id, profile__user=user)
        except (Document.DoesNotExist, ValueError, TypeError):
            from apps.canvas.models import CanvasSession

            try:
                session = (
                    CanvasSession.objects.filter(pk=document_id, profile__user=user)
                    .select_related("document")
                    .first()
                )
                if session:
                    if session.document:
                        return session.document
                    title = f"Canvas Note {session.created_at.strftime('%Y-%m-%d %H:%M')}"
                    document, _ = IngestionService.create_document(
                        user,
                        profile=session.profile,
                        source=Document.Source.CANVAS,
                        source_type=Document.SourceType.CANVAS_PAGE,
                        subject=session.subject,
                        title=title,
                    )
                    CanvasSession.objects.filter(pk=session.pk).update(document=document)
                    session.document = document
                    return document
            except Exception:
                pass
            raise ResourceNotFound("Document not found.")

    @staticmethod
    def get_owned_page(user, page_id, *, for_update: bool = False) -> DocumentPage:
        try:
            qs = DocumentPage.objects.select_related("document")
            if for_update:
                qs = qs.select_for_update()
            return qs.get(pk=page_id, document__profile__user=user)
        except (DocumentPage.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Document page not found.")

    @staticmethod
    def create_document(
        user,
        *,
        profile,
        source: str,
        source_type: str,
        subject=None,
        notebook=None,
        title: str = "",
        filename: str = "",
    ) -> tuple[Document, DocumentPage]:
        document = Document.objects.create(
            profile=profile,
            subject=subject,
            notebook=notebook,
            title=title or filename or "Untitled Note",
            source=source,
            source_type=source_type,
        )
        page = DocumentPage.objects.create(
            document=document,
            page_number=1,
            ocr_attempt_count=0,
            ocr_generation=0,
        )
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
            page = cls.get_owned_page(user, page_id, for_update=True)
            if not page.image_ref or not storage.exists(page.image_ref):
                raise ValidationError("No uploaded object found for this page.")
            data = storage.read_bytes(page.image_ref)
            content_hash = compute_content_hash(data)

            page.ocr_attempt_count = 1
            page.ocr_generation += 1
            page.ocr_started_at = timezone.now()
            page.ocr_status = DocumentPage.OcrStatus.PENDING
            page.review_status = DocumentPage.ReviewStatus.OCR_PENDING
            page.save(update_fields=("ocr_attempt_count", "ocr_generation", "ocr_started_at", "ocr_status", "review_status"))

            revision = cls._create_revision_locked(
                page,
                content_hash=content_hash,
                ocr_status=DocumentPageRevision.OcrStatus.PENDING,
                revision_type="ocr",
            )
            job, created = cls.enqueue_ocr_job(page, revision)

        # Eager dispatch may have finished the job before we respond; refresh
        # so callers never see stale pending state.
        revision.refresh_from_db()
        job.refresh_from_db()
        return {"revision": revision, "job": job, "job_created": created}

    @staticmethod
    def _create_revision_locked(
        page: DocumentPage,
        *,
        content_hash: str,
        ocr_status: str,
        edited_by=None,
        created_by=None,
        parent_revision=None,
        revision_type: str = "ocr",
        snapshot=None,
        text_hash: str = "",
    ) -> DocumentPageRevision:
        with transaction.atomic():
            last_revision = DocumentPageRevision.objects.filter(page=page).select_for_update().order_by("-revision_number").first()
            last_number = last_revision.revision_number if last_revision else 0
            revision = DocumentPageRevision.objects.create(
                page=page,
                revision_number=(last_number or 0) + 1,
                parent_revision=parent_revision or last_revision,
                revision_type=revision_type,
                created_by=created_by or edited_by,
                content_hash=content_hash,
                text_hash=text_hash,
                content_snapshot=snapshot if snapshot is not None else {},
                edited_by=edited_by,
                ocr_status=ocr_status,
            )
            page.current_revision_id = revision.pk
            page.ocr_status = ocr_status
            page.needs_review = ocr_status == DocumentPageRevision.OcrStatus.NEEDS_REVIEW
            page.save(update_fields=("current_revision_id", "ocr_status", "needs_review"))

            # Invalidate active enrichments when note content revision changes
            from apps.ai_classroom.models import EnrichedNote
            EnrichedNote.objects.filter(document=page.document, superseded=False).update(ai_stale=True)
        return revision

    @classmethod
    def create_user_revision(
        cls,
        user,
        document_id,
        page_id,
        lines: list[dict],
        expected_revision_number: Optional[int] = None,
    ) -> DocumentPageRevision:
        """§48: user edits create a new immutable revision; the old one stays."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")

            # Check 1: In-Flight OCR Check (409)
            if page.ocr_status in [DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING]:
                raise RevisionConflict("OCR is currently in progress.")

            # Check 2: Ignored Page Check (422)
            if page.is_ignored:
                raise ValidationError("Page is ignored; un-ignore before editing.")

            # Check 3: Stale Revision Check (409)
            current_rev = page.current_revision.revision_number if page.current_revision else 0
            if expected_revision_number is not None and expected_revision_number != current_rev:
                raise RevisionConflict(
                    f"Stale revision. Current revision is {current_rev}.",
                    details={"latest_revision": current_rev},
                )

            # Check 4: Payload Validation (422)
            max_lines = getattr(settings, "MAX_LINES_PER_PAGE", 500)
            max_line_length = getattr(settings, "MAX_LINE_LENGTH", 1000)

            if not lines:
                raise ValidationError("At least one line is required.")
            if len(lines) > max_lines:
                raise ValidationError(f"Maximum lines per page is {max_lines}.")

            line_indices = [l.get("line_index") for l in lines]
            if line_indices != list(range(len(lines))):
                raise ValidationError("Line indices must be contiguous from 0 to len(lines) - 1.")

            provided_lineages = [str(l["lineage_id"]) for l in lines if l.get("lineage_id")]
            if len(provided_lineages) != len(set(provided_lineages)):
                raise ValidationError("Duplicate lineage_id in payload.")

            current_line_map = (
                {str(l.lineage_id): l for l in page.current_revision.lines.all()}
                if page.current_revision
                else {}
            )
            for lid in provided_lineages:
                if lid not in current_line_map:
                    raise ValidationError(f"Unknown lineage_id {lid} does not belong to current revision.")

            clean_lines = []
            for i, line in enumerate(lines):
                raw_text = line.get("text") or ""
                # Preserve leading spaces/code indentation; strip trailing newlines only
                stored_text = raw_text.rstrip("\r\n")
                if not stored_text.strip():
                    raise ValidationError(f"Line {i} has no text.")
                if len(stored_text) > max_line_length:
                    raise ValidationError(f"Line {i} exceeds maximum length of {max_line_length} characters.")
                clean_lines.append((i, line, stored_text))

            # Check 5: No-Op Save Detection
            if page.current_revision is not None:
                existing_lines = list(page.current_revision.lines.order_by("line_index"))
                if len(existing_lines) == len(clean_lines):
                    is_noop = True
                    for i, (_, raw_l, stored_text) in enumerate(clean_lines):
                        ex = existing_lines[i]
                        raw_lid = str(raw_l.get("lineage_id")) if raw_l.get("lineage_id") else None
                        if str(ex.lineage_id) != raw_lid or ex.text != stored_text:
                            is_noop = False
                            break
                    if is_noop:
                        logger.info(
                            "No-op edit detected for page %s revision %s; returning existing revision.",
                            page.pk,
                            page.current_revision.pk,
                        )
                        return page.current_revision

            # Prepare new revision lines
            parent_rev = page.current_revision
            rev_number = (parent_rev.revision_number + 1) if parent_rev else 1
            lines_to_create = []
            for i, raw_l, stored_text in clean_lines:
                lid_str = str(raw_l.get("lineage_id")) if raw_l.get("lineage_id") else None
                if lid_str:
                    parent_line = current_line_map[lid_str]
                    lineage_id = parent_line.lineage_id
                    original_text = parent_line.original_text or parent_line.text
                    is_edited = (stored_text != parent_line.text) or (stored_text != original_text)
                    is_user_added = False
                    parent_line_id = parent_line.id
                    bbox = parent_line.bbox  # Server-controlled bbox: copy forward
                else:
                    lineage_id = uuid.uuid4()
                    original_text = ""
                    is_edited = False
                    is_user_added = True
                    parent_line_id = None
                    bbox = raw_l.get("bbox")  # Accept client-sent bbox for user-added lines

                lines_to_create.append(
                    {
                        "line_index": i,
                        "stored_text": stored_text,
                        "bbox": bbox,
                        "lineage_id": lineage_id,
                        "original_text": original_text,
                        "is_edited": is_edited,
                        "is_user_added": is_user_added,
                        "parent_line_id": parent_line_id,
                    }
                )

            text_content = "\n".join(l["stored_text"] for l in lines_to_create)
            text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
            snapshot = {
                "lines": [
                    {
                        "line_index": l["line_index"],
                        "text": l["stored_text"],
                        "bbox": l["bbox"],
                        "lineage_id": str(l["lineage_id"]),
                    }
                    for l in lines_to_create
                ],
                "origin": "user_edit",
            }

            revision = DocumentPageRevision.objects.create(
                page=page,
                revision_number=rev_number,
                parent_revision=parent_rev,
                revision_type="user_edit",
                created_by=user,
                edited_by=user,
                content_hash=snapshot_hash(snapshot),
                text_hash=text_hash,
                content_snapshot=snapshot,
                ocr_status=DocumentPageRevision.OcrStatus.COMPLETED,
            )

            DocumentLine.objects.bulk_create(
                [
                    DocumentLine(
                        page_revision=revision,
                        line_index=l["line_index"],
                        text=l["stored_text"],
                        bbox=l["bbox"],
                        confidence_score=None,
                        lineage_id=l["lineage_id"],
                        original_text=l["original_text"],
                        is_edited=l["is_edited"],
                        is_user_added=l["is_user_added"],
                        parent_line_id=l["parent_line_id"],
                    )
                    for l in lines_to_create
                ]
            )

            page.current_revision_id = revision.pk
            if page.is_approved:
                # Editing an approved page keeps it approved
                page.review_status = DocumentPage.ReviewStatus.APPROVED
                page.needs_review = False
                page.index_epoch += 1
                page.save(update_fields=("current_revision_id", "review_status", "needs_review", "index_epoch"))
                sync_page_approval_and_indexing(page.document, page)
            else:
                page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW
                page.needs_review = False
                if page.ocr_status == DocumentPage.OcrStatus.FAILED:
                    page.ocr_generation += 1
                page.save(update_fields=("current_revision_id", "review_status", "needs_review", "ocr_generation"))
                sync_page_approval_and_indexing(page.document, page)

            return revision

    @classmethod
    def approve_page(
        cls,
        user,
        document_id,
        page_id,
        expected_revision_number: Optional[int] = None,
    ) -> tuple[DocumentPage, bool]:
        """Approve a page's transcript and enqueue indexing if approved."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")

            # Check 1: Ignored Page Check (422)
            if page.is_ignored:
                raise ValidationError("Page is ignored; un-ignore before approving.")

            # Check 2: In-Flight OCR Check (409)
            if page.ocr_status in [DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING]:
                raise RevisionConflict("OCR is currently in progress.")

            # Check 3: Failed OCR Check (422)
            if page.ocr_status == DocumentPage.OcrStatus.FAILED and page.current_revision is None:
                raise ValidationError("Cannot approve a failed page without transcription.")

            # Check 4: Blank Page Check (422)
            if page.current_revision and not page.current_revision.lines.exists():
                raise ValidationError("Cannot approve a blank page; use Ignore for blank pages.")

            # Check 5: Stale Revision Check (409)
            current_rev = page.current_revision.revision_number if page.current_revision else 0
            if expected_revision_number is not None and expected_revision_number != current_rev:
                raise RevisionConflict(
                    f"Stale revision. Current revision is {current_rev}.",
                    details={"latest_revision": current_rev},
                )

            # Conditional update idempotency: if page was already approved, update 0 rows
            rows_updated = DocumentPage.objects.filter(
                id=page.id,
                is_approved=False,
            ).update(
                is_approved=True,
                review_status=DocumentPage.ReviewStatus.APPROVED,
                approved_at=timezone.now(),
                approved_by=user,
                needs_review=False,
            )

            doc = page.document
            unapproved_count = doc.pages.filter(is_approved=False, is_ignored=False).count()
            all_approved = (unapproved_count == 0)

            if rows_updated == 0:
                # Page is already approved; return 200 idempotent no-op
                page.refresh_from_db()
                return page, all_approved

            page.refresh_from_db()
            page.index_epoch += 1
            page.save(update_fields=("index_epoch",))

            sync_page_approval_and_indexing(doc, page)
            return page, all_approved

    @classmethod
    def reopen_page(cls, user, document_id, page_id) -> DocumentPage:
        """Moves approved page back to pending_review, deactivates chunks, resyncs descriptor."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")
            if page.is_ignored:
                raise ValidationError("Page is ignored; un-ignore before reopening.")
            if page.ocr_status in [DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING]:
                raise RevisionConflict("OCR is currently in progress.")

            page.is_approved = False
            page.approved_at = None
            page.approved_by = None
            page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW
            page.save(update_fields=("is_approved", "approved_at", "approved_by", "review_status"))

            sync_page_approval_and_indexing(page.document, page)
            return page

    @classmethod
    def ignore_page(cls, user, document_id, page_id) -> DocumentPage:
        """Marks page as ignored, clears approval and index hash, deactivates chunks."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")
            if page.ocr_status in [DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING]:
                raise RevisionConflict("OCR is currently in progress.")

            page.is_ignored = True
            page.is_approved = False
            page.approved_at = None
            page.approved_by = None
            page.indexed_text_hash = ""
            page.save(update_fields=("is_ignored", "is_approved", "approved_at", "approved_by", "indexed_text_hash"))

            sync_page_approval_and_indexing(page.document, page)
            return page

    @classmethod
    def unignore_page(cls, user, document_id, page_id) -> DocumentPage:
        """Removes ignored status from page, leaving it pending review."""
        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")

            page.is_ignored = False
            page.is_approved = False
            page.review_status = DocumentPage.ReviewStatus.PENDING_REVIEW
            page.save(update_fields=("is_ignored", "is_approved", "review_status"))

            sync_page_approval_and_indexing(page.document, page)
            return page

    @classmethod
    def retry_page_ocr(cls, user, document_id, page_id, force: bool = False) -> tuple[DocumentPage, Job]:
        """Re-run OCR for a specific page using the fixed preprocessing ladder and attempt cap."""
        from providers.registry import get_object_storage
        from apps.jobs.services import dispatch_job, get_or_create_job

        with transaction.atomic():
            page = cls.get_owned_page(user, page_id, for_update=True)
            if str(page.document_id) != str(document_id):
                raise ValidationError("Page does not belong to this document.")

            # Check 1: Ignored page check (422)
            if page.is_ignored:
                raise ValidationError("Page is ignored; un-ignore before retrying OCR.")

            # Check 2: In-flight OCR check (409)
            if page.ocr_status in [DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING]:
                raise RevisionConflict("OCR is currently in progress.")

            # Check 3: Approved page guard (409)
            if page.review_status == DocumentPage.ReviewStatus.APPROVED or page.is_approved:
                raise RevisionConflict("Page is approved; reopen before retrying OCR.")

            # Check 4: User-edit conflict guard (409)
            if page.current_revision and page.current_revision.revision_type == "user_edit" and not force:
                raise RevisionConflict("Page has user edits; pass force=true to re-run OCR.")

            # Check 5: Attempt cap (422)
            max_attempts = getattr(settings, "MAX_OCR_ATTEMPTS", 3)
            if page.ocr_attempt_count >= max_attempts:
                raise ValidationError(f"Maximum OCR attempts ({max_attempts}) reached for this page.")

            storage = get_object_storage()
            ladder_step = page.ocr_attempt_count + 1

            # If this is a canvas page, re-render strokes according to the preprocessing ladder
            if page.document.source == Document.Source.CANVAS:
                from apps.canvas.models import CanvasSession, CanvasPage
                from apps.canvas.raster import render_strokes_png, CANVAS_W, CANVAS_H

                session = CanvasSession.objects.filter(document_id=page.document_id).first()
                if session:
                    cpage = CanvasPage.objects.filter(session=session, page_number=page.page_number).first()
                    if cpage:
                        strokes = list(cpage.strokes.order_by("sequence_order").values_list("points", flat=True))
                        scale = 1.5 if ladder_step == 2 else (2.0 if ladder_step >= 3 else 1.0)
                        png = render_strokes_png(strokes, width=int(CANVAS_W * scale), height=int(CANVAS_H * scale))
                        key = f"{session.profile_id}/{page.id}.png"
                        storage.store_bytes(key, png)
                        page.image_ref = key
                        if not cpage.is_finalized:
                            cpage.is_finalized = True
                            cpage.finalized_at = timezone.now()
                            cpage.save(update_fields=("is_finalized", "finalized_at"))

            if not page.image_ref or not storage.exists(page.image_ref):
                raise ValidationError("Page image file does not exist in storage.")

            content_bytes = storage.read_bytes(page.image_ref)
            content_hash = compute_content_hash(content_bytes)

            page.ocr_attempt_count += 1
            page.ocr_generation += 1
            page.ocr_started_at = timezone.now()
            page.ocr_status = DocumentPage.OcrStatus.PENDING
            page.review_status = DocumentPage.ReviewStatus.OCR_PENDING
            page.is_approved = False
            page.approved_at = None
            page.approved_by = None
            page.needs_review = False

            last_revision = DocumentPageRevision.objects.filter(page=page).order_by("-revision_number").first()
            last_number = last_revision.revision_number if last_revision else 0
            revision = DocumentPageRevision.objects.create(
                page=page,
                revision_number=last_number + 1,
                parent_revision=last_revision,
                revision_type="ocr",
                content_hash=content_hash,
                ocr_status=DocumentPageRevision.OcrStatus.PENDING,
            )
            page.current_revision_id = revision.pk
            page.save(
                update_fields=(
                    "ocr_attempt_count",
                    "ocr_generation",
                    "ocr_started_at",
                    "ocr_status",
                    "review_status",
                    "is_approved",
                    "approved_at",
                    "approved_by",
                    "needs_review",
                    "current_revision_id",
                    "image_ref",
                )
            )

            idempotency_key = f"ocr:{page.pk}:rev_{revision.revision_number}:{revision.content_hash}:{_pipeline_version()}"
            job, created = get_or_create_job(
                job_type="ocr",
                resource_type="document_page_revision",
                resource_id=str(revision.pk),
                profile_id=page.document.profile_id,
                revision_id=revision.pk,
                idempotency_key=idempotency_key,
            )
            if not created and job.status != Job.Status.QUEUED:
                Job.objects.filter(pk=job.pk).update(
                    status=Job.Status.QUEUED, next_retry_at=None, last_error=""
                )
                job.refresh_from_db()
            dispatch_job(job)

            return page, job


def run_ocr_job(job: Job) -> None:
    """Worker flow (§47). Runs inside the trusted RLS context established by the executor.
    Invariant: OCR completion NEVER enqueues index or enrichment jobs.
    """
    from providers.registry import get_object_storage, get_ocr_provider
    from apps.documents.validation import compute_image_metrics, evaluate_page_review_status

    try:
        revision = DocumentPageRevision.objects.select_related("page", "page__document").get(pk=job.resource_id)
    except (DocumentPageRevision.DoesNotExist, Document.DoesNotExist):
        logger.info("OCR job %s target revision %s no longer exists (document deleted); skipping.", job.pk, job.resource_id)
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status",))
        return

    page = revision.page
    if not page or not page.document_id:
        logger.info("OCR job %s page or document no longer exists; skipping.", job.pk)
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status",))
        return

    # Idempotency inside the handler: completed revisions are not re-OCRed.
    if revision.ocr_status == DocumentPageRevision.OcrStatus.COMPLETED and revision.lines.exists():
        return

    storage = get_object_storage()
    if not page.image_ref or not storage.exists(page.image_ref):
        raise ValidationError("Image object missing for OCR.")

    generation_token = page.ocr_generation
    now = timezone.now()
    DocumentPageRevision.objects.filter(pk=revision.pk).update(
        ocr_status=DocumentPageRevision.OcrStatus.PROCESSING
    )
    DocumentPage.objects.filter(pk=page.pk).update(
        ocr_status=DocumentPage.OcrStatus.PROCESSING,
        review_status=DocumentPage.ReviewStatus.OCR_PROCESSING,
        ocr_started_at=now,
    )

    request_id = f"job_{job.pk}"
    chain = get_ocr_provider()
    try:
        result, attempted = chain.recognize(page.image_ref, request_id=request_id)
    except SoftTimeLimitExceeded:
        logger.warning("OCR job %s exceeded soft time limit", job.pk)
        DocumentPageRevision.objects.filter(pk=revision.pk).update(
            ocr_status=DocumentPageRevision.OcrStatus.FAILED,
            error_message="OCR worker time limit exceeded",
        )
        DocumentPage.objects.filter(pk=page.pk).update(
            ocr_status=DocumentPage.OcrStatus.FAILED,
            review_status=DocumentPage.ReviewStatus.OCR_FAILED,
        )
        DocumentPage.objects.filter(pk=page.pk).update(ocr_generation=page.ocr_generation + 1)
        raise
    except Exception as exc:
        DocumentPageRevision.objects.filter(pk=revision.pk).update(
            ocr_status=DocumentPageRevision.OcrStatus.FAILED,
            error_message=str(exc)[:500],
        )
        DocumentPage.objects.filter(pk=page.pk).update(
            ocr_status=DocumentPage.OcrStatus.FAILED,
            review_status=DocumentPage.ReviewStatus.OCR_FAILED,
        )
        raise

    lines = sorted(result.lines or [], key=lambda l: l.get("line_index", 0))
    image_bytes = storage.read_bytes(page.image_ref)
    image_metrics = compute_image_metrics(image_bytes)
    review_status, review_reasons = evaluate_page_review_status(
        lines, image_metrics, source_type=page.document.source_type
    )
    needs_review = (review_status == DocumentPage.ReviewStatus.NEEDS_REVIEW)

    # One transaction: claim result + lines + status + review workflow state with generation check.
    with transaction.atomic():
        locked_page = DocumentPage.objects.select_for_update().get(pk=page.pk)
        if locked_page.ocr_generation != generation_token:
            logger.warning(
                "OCR job %s discarded: generation token %s != page generation %s",
                job.pk,
                generation_token,
                locked_page.ocr_generation,
            )
            return

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
                    lineage_id=uuid.uuid4(),
                    original_text=line["text"],
                    is_edited=False,
                    is_user_added=False,
                    parent_line_id=None,
                )
                for i, line in enumerate(lines)
            ]
        )
        text_content = "\n".join(l["text"] for l in lines)
        text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        revision.content_snapshot = {"lines": lines, "attempted_providers": attempted}
        revision.ocr_provider = result.provider
        revision.ocr_status = (
            DocumentPageRevision.OcrStatus.NEEDS_REVIEW
            if needs_review
            else DocumentPageRevision.OcrStatus.COMPLETED
        )
        revision.review_reasons = review_reasons
        revision.text_hash = text_hash
        revision.save(update_fields=("content_snapshot", "ocr_provider", "ocr_status", "review_reasons", "text_hash"))

        locked_page.needs_review = needs_review
        locked_page.ocr_status = revision.ocr_status
        locked_page.review_status = review_status
        locked_page.save(update_fields=("needs_review", "ocr_status", "review_status"))

    logger.info(
        "OCR job %s completed via %s (%s lines, review=%s, review_status=%s, reasons=%s)",
        job.pk,
        attempted,
        len(lines),
        needs_review,
        review_status,
        review_reasons,
    )
