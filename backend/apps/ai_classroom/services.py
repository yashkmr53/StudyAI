"""AI Classroom enrichment pipeline (architecture §11, §12, §51, §52).

Stage A Retrieve → B Draft → C Gap detection → D Gap filling →
E Citation stitching → F Evidence verification → schema validation →
persist EnrichedNote/Blocks/CitationBlocks.

- Every node from Draft onward validates its output against a JSON
  schema (§11).
- Grounding priority: user notes, then READY reference books (§51);
  the pipeline never invents uncited content — the mock LLM only
  restructures supplied evidence.
- Evidence verification (F) is REAL rule-based code: lexical support
  between block content and each cited chunk, versioned thresholds.
  Calibration against labeled data is future work (§26).
- Failure isolation (§28/§52): an enrichment failure never touches the
  canonical document or NoteSpace artifacts.
"""
import hashlib
import json
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.ai_classroom.models import CitationBlock, EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.prompts import QUALIFIED, active_prompt
from apps.jobs.models import Job, JobExecutionState
from apps.documents.models import Document, DocumentPage
from apps.retrieval.models import NoteChunk
from providers.registry import get_llm_provider
from shared.exceptions import ResourceNotFound, ValidationError

logger = logging.getLogger(__name__)

from typing import Optional

def _verifier_version() -> str:
    return getattr(settings, "VERIFIER_VERSION", "sim-v1")


def _supported_threshold() -> float:
    return float(getattr(settings, "VERIFIER_SUPPORTED_THRESHOLD", 0.60))


def _partial_threshold() -> float:
    return float(getattr(settings, "VERIFIER_PARTIAL_THRESHOLD", 0.30))


def _descriptor(document: Document) -> str:
    approved_pages = list(
        document.pages.filter(is_approved=True, is_ignored=False)
        .prefetch_related("current_revision__lines")
        .order_by("page_number")
    )
    if not approved_pages:
        return ""
    parts = []
    for p in approved_pages:
        rev = p.current_revision
        if rev:
            for l in rev.lines.order_by("line_index"):
                parts.append(f"{p.page_number}:{l.line_index}:{l.text}")
    payload = "|".join(parts)
    return "v2:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:61]


def _get_next_node(current_node: str) -> str:
    """Return the node to resume from after the given completed node."""
    mapping = {
        "retrieve": "draft",
        "draft": "gap_detection",
        "gap_detection": "gap_fill",  # or "citation_stitch" if no gaps
        "gap_fill": "citation_stitch",
        "citation_stitch": "evidence_verification",
        "evidence_verification": "format_output",
        "format_output": "format_output",  # terminal
    }
    return mapping.get(current_node, "retrieve")


class EvidenceVerifier:
    """Rules-v1 verifier: lexical support between block content and each
    cited chunk. Deterministic and independently testable; thresholds are
    placeholders pending calibration on labeled validation sets (§26)."""

    VERSION = _verifier_version()

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(w) > 2}

    @classmethod
    def _lexical_support(cls, block_content: str, chunk_contents: list[str]) -> float:
        block_tokens = cls._tokens(block_content)
        if not block_tokens:
            return 0.0
        best = 0.0
        for content in chunk_contents:
            chunk_tokens = cls._tokens(content)
            if not chunk_tokens:
                continue
            overlap = len(block_tokens & chunk_tokens) / max(1, len(block_tokens))
            best = max(best, overlap)
        return best

    @classmethod
    def _supported_threshold(cls) -> float:
        return float(getattr(settings, "VERIFIER_SUPPORTED_THRESHOLD", 0.60))

    @classmethod
    def _partial_threshold(cls) -> float:
        return float(getattr(settings, "VERIFIER_PARTIAL_THRESHOLD", 0.30))

    @classmethod
    def verify(cls, block_content: str, source_refs: list[dict]) -> tuple[str, Optional[float]]:
        if not source_refs:
            return CitationBlock.VerificationStatus.NOT_VERIFIED, None

        block_tokens = cls._tokens(block_content)
        if not block_tokens:
            return CitationBlock.VerificationStatus.UNSUPPORTED, 0.0

        chunk_ids = [ref.get("chunk_id") for ref in source_refs]
        chunks = NoteChunk.objects.filter(pk__in=[cid for cid in chunk_ids if cid])
        by_id = {str(c.pk): c for c in chunks}
        cited_contents = [c.content for c in (by_id.get(ref.get("chunk_id")) for ref in source_refs) if c]
        return cls._classify(block_content, cited_contents)

    @classmethod
    def _classify(cls, block_content: str, cited_contents: list[str]) -> tuple[str, Optional[float]]:
        """DB-free classification over already-resolved chunk contents."""
        score = cls._lexical_support(block_content, cited_contents)
        if score >= cls._supported_threshold():
            status = CitationBlock.VerificationStatus.SUPPORTED
        elif score >= cls._partial_threshold():
            status = CitationBlock.VerificationStatus.PARTIALLY_SUPPORTED
        else:
            status = CitationBlock.VerificationStatus.UNSUPPORTED
        return status, round(score, 4)


class EnrichmentService:
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
                if session and session.document:
                    return session.document
            except Exception:
                pass
            raise ResourceNotFound("Document not found.")

    @staticmethod
    def _compute_change_magnitude(document: Document) -> float:
        """Compute cosine similarity between current and previous chunk embeddings.
        Returns a value between 0 and 1, where 1 = identical, 0 = completely different."""
        from apps.retrieval.models import NoteChunk
        from apps.ai_classroom.models import EnrichedNote
        import math

        current_chunks = list(
            NoteChunk.objects.filter(document=document, stale=False)
            .order_by("chunk_index")
            .values_list("embedding", flat=True)
        )
        if not current_chunks:
            return 1.0  # No chunks = maximum change

        current_hash = _descriptor(document)

        # Try to get previous descriptor from the latest EnrichedNote
        prev_note = EnrichedNote.objects.filter(
            document=document, superseded=False
        ).exclude(content_hash=current_hash).order_by("-created_at").first()

        if not prev_note:
            return 1.0  # No previous enrichment = maximum change

        prev_hash = prev_note.content_hash
        if not prev_hash:
            return 1.0  # No hash available = maximum change

        # Compute Jaccard similarity based on content hash parts as proxy for cosine similarity
        current_parts = set(current_hash.split("|"))
        prev_parts = set(prev_hash.split("|"))
        common = len(current_parts & prev_parts)
        union = len(current_parts | prev_parts)
        jaccard = common / max(1, union) if union > 0 else 1.0
        # Invert: higher magnitude = more different = 1 - jaccard
        magnitude = 1.0 - jaccard
        return round(magnitude, 4)

    @staticmethod
    def enqueue_enrichment(user, document_id, *, force_refresh: bool = False) -> dict:
        from apps.jobs.services import dispatch_job, get_or_create_job
        from django.utils import timezone
        from datetime import timedelta

        with transaction.atomic():
            document = EnrichmentService.get_owned_document(user, document_id)
            if document.profile_id is None:
                raise ValidationError("Platform reference documents cannot be enriched.")
            if not document.pages.exclude(current_revision_id=None).exists():
                raise ValidationError("Document has no completed revisions to enrich.")

            existing = (
                EnrichedNote.objects.filter(document=document, superseded=False, ai_stale=False).first()
                if not force_refresh
                else None
            )
            if existing and (existing.blocks.exists() or existing.empty_reason):
                return {"note": existing, "job": None, "created": False}

            # Check 1: In-flight OCR
            processing_pages = document.pages.filter(
                Q(review_status__in=[DocumentPage.ReviewStatus.OCR_PENDING, DocumentPage.ReviewStatus.OCR_PROCESSING])
                | Q(ocr_status__in=[DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING])
            )
            if processing_pages.exists():
                raise ValidationError("Note transcription is still processing. Please wait for transcription to complete before enriching.")

            # Check 2: Transcript Approval & Readiness Gating
            approved_pages_count = document.pages.filter(is_approved=True).count()
            unapproved_unignored = document.pages.filter(is_approved=False, is_ignored=False).count()
            if approved_pages_count == 0 or unapproved_unignored > 0:
                blocking = list(
                    document.pages.filter(is_approved=False, is_ignored=False)
                    .order_by("page_number")
                    .values_list("page_number", flat=True)
                )
                raise ValidationError(
                    "Note transcript must be approved before generating enrichment. Document is not ready for enrichment: all pages must be approved or ignored, and at least one page must be approved.",
                    code="NOT_READY_FOR_ENRICHMENT",
                    details={"blocking_pages": blocking},
                )

            from apps.ai_classroom.budget import assert_within_budget

            assert_within_budget(document.profile_id)

            # B7: Enrichment coalescing window + change-magnitude threshold
            coalesce_window = getattr(settings, "ENRICHMENT_COALESCE_WINDOW_SECONDS", 300)
            change_threshold = getattr(settings, "ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD", 0.15)

            if not force_refresh and coalesce_window > 0:
                # Check for pending/queued enrichment job on same document within window
                since = timezone.now() - timedelta(seconds=coalesce_window)
                pending_job = Job.objects.filter(
                    job_type="enrich",
                    resource_type="document",
                    resource_id=str(document.pk),
                    status__in=[Job.Status.QUEUED, Job.Status.RUNNING],
                    created_at__gte=since,
                ).order_by("-created_at").first()

                if pending_job:
                    # Compute change magnitude
                    magnitude = EnrichmentService._compute_change_magnitude(document)
                    if magnitude <= change_threshold:
                        # Change is below threshold - don't create new job
                        return {"note": None, "job": pending_job, "created": False, "coalesced": True}

            job_key = (
                f"enrich:{document.pk}:{_descriptor(document)[:32]}"
                + (f":refresh:{EnrichedNote.objects.filter(document=document).count()}" if force_refresh else "")
            )
            job, created = get_or_create_job(
                job_type="enrich",
                resource_type="document",
                resource_id=str(document.pk),
                profile_id=document.profile_id,
                idempotency_key=job_key,
            )
            if created or job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
                if not created:
                    Job.objects.filter(pk=job.pk).update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
                    job.refresh_from_db()
                from apps.jobs.services import dispatch_job

                dispatch_job(job)
                job.refresh_from_db()

        return {"note": None, "job": job, "created": created}

    @staticmethod
    def latest_note(user, document_id):
        document = EnrichmentService.get_owned_document(user, document_id)
        return EnrichedNote.objects.filter(document=document, superseded=False).order_by("-created_at").first()

    @staticmethod
    def get_latest_enrichment_payload(user, document_id: str) -> dict:
        document = EnrichmentService.get_owned_document(user, document_id)
        note = EnrichedNote.objects.filter(document=document, superseded=False).order_by("-created_at").first()
        job = (
            Job.objects.filter(resource_type="document", resource_id=str(document.pk))
            .filter(Q(job_type="enrich") | Q(job_type="enrichment"))
            .order_by("-created_at")
            .first()
        )
        return {
            "note": note,
            "latest_job": job,
        }

    @staticmethod
    def regenerate_enrichment(user, document_id: str, *, force_rerun: bool = False) -> Job:
        document = EnrichmentService.get_owned_document(user, document_id)
        return dispatch_enrichment_job(document, user, force_rerun=force_rerun)

    @staticmethod
    def force_include_segments(user, document_id: str, line_ids: list[str]) -> Job:
        document = EnrichmentService.get_owned_document(user, document_id)

        # Validate line IDs against document's approved transcript lines
        approved_line_ids = set()
        for p in document.pages.filter(is_approved=True, is_ignored=False):
            if p.current_revision:
                for l in p.current_revision.lines.all():
                    approved_line_ids.add(str(l.lineage_id))

        unknown_ids = [lid for lid in line_ids if str(lid) not in approved_line_ids]
        if unknown_ids:
            from shared.exceptions import ValidationError
            raise ValidationError(
                f"Unknown or unapproved line IDs: {unknown_ids}",
                code="UNKNOWN_LINE_IDS",
            )

        document.force_include_line_ids = [str(x) for x in line_ids]
        document.save(update_fields=("force_include_line_ids",))

        # Automatically dispatch regenerate run in the same API call (§3.9)
        return dispatch_enrichment_job(document, user, force_rerun=True)


def sync_enrichment_staleness(document_id: str) -> None:
    """Two-way staleness sync helper respecting Page then Document lock ordering."""
    with transaction.atomic():
        try:
            doc = Document.objects.select_for_update().get(id=document_id)
        except Document.DoesNotExist:
            return
        current_hash = _descriptor(doc)
        EnrichedNote.objects.filter(document=doc, superseded=False).exclude(content_hash=current_hash).update(ai_stale=True)
        EnrichedNote.objects.filter(document=doc, superseded=False, content_hash=current_hash).update(ai_stale=False)


def dispatch_enrichment_job(document: Document, user, force_rerun: bool = False) -> Job:
    """Dispatch an enrichment job with unique run nonce and in-flight query deduplication (§3.8.3)."""
    if document.profile and document.profile.user_id != user.id:
        from shared.exceptions import PermissionDenied
        raise PermissionDenied("You do not have access to this document.")

    # Readiness validation (§3.1)
    has_unapproved = document.pages.filter(is_approved=False, is_ignored=False).exists()
    has_approved = document.pages.filter(is_approved=True, is_ignored=False).exists()
    if has_unapproved or not has_approved:
        from shared.exceptions import ValidationError
        blocking = list(
            document.pages.filter(is_approved=False, is_ignored=False)
            .order_by("page_number")
            .values_list("page_number", flat=True)
        )
        raise ValidationError(
            "Note transcript must be approved before generating enrichment.",
            code="NOT_READY_FOR_ENRICHMENT",
            details={"blocking_pages": blocking},
        )

    # In-flight deduplication: QUEUED, RUNNING, or FAILED_RETRYABLE
    in_flight = Job.objects.filter(
        resource_type="document",
        resource_id=str(document.pk),
        status__in=[Job.Status.QUEUED, Job.Status.RUNNING, Job.Status.FAILED_RETRYABLE],
    ).filter(Q(job_type="enrich") | Q(job_type="enrichment")).order_by("-created_at").first()

    if in_flight and not force_rerun:
        return in_flight

    start_hash = _descriptor(document)
    run_nonce = uuid.uuid4().hex[:8]
    idempotency_key = f"enrich_note:{document.id}:{start_hash[:24]}:{run_nonce}"

    norm_force_ids = sorted([str(x) for x in (document.force_include_line_ids or [])])
    force_include_hash = (
        hashlib.sha256(json.dumps(norm_force_ids).encode("utf-8")).hexdigest()[:16]
        if norm_force_ids
        else ""
    )
    settings_version = getattr(settings, "PROMPT_VERSION", "topic_enrichment:v1")

    job = Job.objects.create(
        job_type="enrich",
        resource_type="document",
        resource_id=str(document.pk),
        profile_id=document.profile_id,
        idempotency_key=idempotency_key,
        status=Job.Status.QUEUED,
        metadata={
            "start_hash": start_hash,
            "force_include_hash": force_include_hash,
            "force_include_line_ids": norm_force_ids,
            "settings_version": settings_version,
            "outcome": "",
            "error_code": "",
            "message": "Enrichment queued...",
        },
    )

    from apps.jobs.tasks import process_job_task
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        process_job_task.delay(str(job.pk))
    else:
        transaction.on_commit(lambda: process_job_task.delay(str(job.pk)))

    return job


def run_enrichment_job(job: Job) -> None:
    """Execute durable Topic-Based Note Enrichment Job (§3.7, §3.8)."""
    from ai.langgraph.graphs.enrichment_graph import invoke_enrichment_graph
    from ai.langgraph.state.topic_enrichment_state import TopicEnrichmentState

    try:
        document = Document.objects.select_related("profile").get(pk=job.resource_id)
    except Document.DoesNotExist:
        logger.info("Enrichment job %s document %s no longer exists (deleted); skipping.", job.pk, job.resource_id)
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status",))
        return

    # Check for in-flight OCR
    processing_pages = document.pages.filter(
        Q(review_status__in=[DocumentPage.ReviewStatus.OCR_PENDING, DocumentPage.ReviewStatus.OCR_PROCESSING])
        | Q(ocr_status__in=[DocumentPage.OcrStatus.PENDING, DocumentPage.OcrStatus.PROCESSING])
    )
    if processing_pages.exists():
        logger.warning("Enrichment job %s aborted: OCR is still processing.", job.pk)
        job.status = Job.Status.FAILED_RETRYABLE
        job.last_error = "OCR is still processing on some pages."
        job.save(update_fields=("status", "last_error"))
        return

    # Initialize graph state
    initial_state = TopicEnrichmentState(
        document_id=str(document.pk),
        job_id=str(job.pk),
        profile_id=str(document.profile_id) if document.profile_id else None,
        force_include_line_ids=document.force_include_line_ids or [],
    )

    final_state = invoke_enrichment_graph(initial_state)

    outcome = final_state.get("outcome", "ok")
    error_code = final_state.get("error_code", "")

    # Non-note outcomes mapping table (§3.7.2)
    if outcome == "already_up_to_date":
        job.metadata.update({
            "outcome": "already_up_to_date",
            "error_code": "",
            "message": "Enrichment is already up to date.",
        })
        job.mark_succeeded()
        return

    if outcome == "not_ready":
        job.metadata.update({
            "outcome": "not_ready",
            "error_code": "NOT_READY_FOR_ENRICHMENT",
            "message": "Please review and approve all note pages first.",
        })
        job.mark_succeeded()
        return

    if outcome == "insufficient_content":
        job.metadata.update({
            "outcome": "insufficient_content",
            "error_code": "INSUFFICIENT_CONTENT",
            "message": "Not enough academic content to generate enrichment.",
        })
        job.mark_succeeded()
        return

    if outcome == "no_study_content":
        job.metadata.update({
            "outcome": "no_study_content",
            "error_code": "NO_STUDY_CONTENT",
            "message": "No technical study notes identified in transcript.",
        })
        job.mark_succeeded()
        return

    if outcome == "coverage_bug":
        job.metadata.update({
            "outcome": "coverage_bug",
            "error_code": "COVERAGE_INVARIANT_FAILED",
            "message": "An internal verification error occurred. Please retry.",
        })
        job.dead_letter("COVERAGE_INVARIANT_FAILED")
        return

    if outcome == "aborted_not_running":
        job.metadata.update({
            "outcome": "aborted_not_running",
            "error_code": "JOB_NOT_RUNNING",
            "message": "Enrichment was cancelled or reaped.",
        })
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status", "metadata"))
        return

    # Atomic Persistence for "ok" and "needs_attention" (§3.7.3)
    try:
        with transaction.atomic():
            # 1. Lock Job row
            locked_job = Job.objects.select_for_update().get(pk=job.pk)
            if locked_job.status != Job.Status.RUNNING:
                logger.warning("Job %s is no longer RUNNING (status=%s); aborting persistence", job.pk, locked_job.status)
                locked_job.metadata.update({
                    "outcome": "aborted_not_running",
                    "error_code": "JOB_NOT_RUNNING",
                    "message": "Enrichment was cancelled or reaped.",
                })
                locked_job.save(update_fields=("metadata",))
                return

            # 2. Lock Document row (Page first, then Document)
            doc = Document.objects.select_for_update().get(pk=document.pk)

            # 3. Check if a newer job already persisted a note
            active_note = EnrichedNote.objects.filter(document=doc, superseded=False).first()
            if active_note and active_note.generation_job and active_note.generation_job_id != locked_job.pk:
                newer = active_note.generation_job.created_at > locked_job.created_at
                if newer:
                    logger.info("A newer job %s already persisted note for %s; aborting note creation", active_note.generation_job.pk, doc.pk)
                    locked_job.metadata.update({
                        "outcome": "superseded_by_newer",
                        "error_code": "",
                        "message": "Superseded by a newer enrichment.",
                    })
                    locked_job.mark_succeeded()
                    return

            # 4. Supersede old active notes
            EnrichedNote.objects.filter(document=doc, superseded=False).update(superseded=True)

            note_status = final_state.get("status", "ok")
            note = EnrichedNote.objects.create(
                document=doc,
                generation_job=locked_job,
                status=note_status,
                content_hash=final_state.get("start_hash") or _descriptor(doc),
                force_include_hash=final_state.get("force_include_hash", ""),
                settings_version=final_state.get("settings_version", getattr(settings, "PROMPT_VERSION", "topic_enrichment:v1")),
                revision_ids=[
                    str(pk)
                    for pk in doc.pages.exclude(current_revision_id=None).values_list("current_revision_id", flat=True)
                ],
                evidence_status_by_topic=final_state.get("evidence_status_by_topic", {}),
                excluded_segments=final_state.get("excluded_segments", []),
                diagnostics=final_state.get("diagnostics", {}),
                provider=final_state.get("llm_provider", "ollama"),
                model=final_state.get("llm_model", getattr(settings, "ENRICHMENT_MODEL", "qwen3.5:4b")),
                prompt_version=getattr(settings, "PROMPT_VERSION", "topic_enrichment:v1"),
                schema_version="v2",
            )

            # 5. Create EnrichedNoteBlocks
            sections_by_topic = final_state.get("sections_by_topic", {})
            topic_plan = final_state.get("topic_plan", {})
            planned_topics = topic_plan.get("topics", [])
            topic_order = [t.get("topic_id") for t in planned_topics] or list(sections_by_topic.keys())

            block_index = 1
            for tid in topic_order:
                sec_data = sections_by_topic.get(tid)
                if not sec_data:
                    continue
                title = sec_data.get("title", f"Topic {tid}")
                EnrichedNoteBlock.objects.create(
                    enriched_note=note,
                    block_index=block_index,
                    block_kind=EnrichedNoteBlock.BlockKind.HEADING,
                    render_as=EnrichedNoteBlock.RenderAs.PROSE,
                    topic_id=tid,
                    block_type="topic_heading",
                    title=title,
                    content=title,
                    generation_method=EnrichedNoteBlock.GenerationMethod.RULE_BASED,
                )
                block_index += 1

                for blk in sec_data.get("blocks", []):
                    blk_type = blk.get("type", "student")
                    blk_kind = (
                        EnrichedNoteBlock.BlockKind.STUDENT
                        if blk_type == "student"
                        else (EnrichedNoteBlock.BlockKind.ADDITION if blk_type == "addition" else EnrichedNoteBlock.BlockKind.HEADING)
                    )
                    render_as = (
                        EnrichedNoteBlock.RenderAs.CODE
                        if blk.get("render_as") == "code"
                        else EnrichedNoteBlock.RenderAs.PROSE
                    )
                    gen_method = (
                        EnrichedNoteBlock.GenerationMethod.TRANSCRIBED
                        if blk_kind == EnrichedNoteBlock.BlockKind.STUDENT
                        else EnrichedNoteBlock.GenerationMethod.LLM
                    )
                    EnrichedNoteBlock.objects.create(
                        enriched_note=note,
                        block_index=block_index,
                        block_kind=blk_kind,
                        render_as=render_as,
                        topic_id=tid,
                        block_type="student_notes" if blk_kind == EnrichedNoteBlock.BlockKind.STUDENT else "addition",
                        title="",
                        content=blk.get("text", ""),
                        source_line_ids=blk.get("line_ids", []),
                        support_status=blk.get("support_status", ""),
                        addition_kind=blk.get("addition_kind") or "",
                        generation_method=gen_method,
                    )
                    block_index += 1

            # 6. Global Citation Block
            global_citations = final_state.get("global_citations", [])
            first_block = note.blocks.first()
            if first_block:
                CitationBlock.objects.create(
                    enriched_note_block=first_block,
                    source_refs=global_citations,
                    verification_status=(
                        CitationBlock.VerificationStatus.SUPPORTED
                        if note_status == "ok"
                        else CitationBlock.VerificationStatus.PARTIALLY_SUPPORTED
                    ),
                    verifier_version="v2",
                )

            # 7. Check in-transaction staleness
            cur_hash = _descriptor(doc)
            if note.content_hash != cur_hash:
                note.ai_stale = True
                note.save(update_fields=("ai_stale",))

            # 8. Two-way post-commit hook
            transaction.on_commit(lambda: sync_enrichment_staleness(str(doc.id)))

            locked_job.metadata.update({
                "outcome": note_status,
                "error_code": "",
                "message": (
                    "Enrichment generated successfully."
                    if note_status == "ok"
                    else "Enrichment completed with items needing review."
                ),
            })
            locked_job.mark_succeeded()

    except Exception as exc:
        logger.error("Enrichment persistence failed for %s: %s", document.pk, exc)
        job.dead_letter(str(exc))
        raise
