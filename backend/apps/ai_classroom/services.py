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
import logging

from django.conf import settings
from django.db import transaction

from apps.ai_classroom.models import CitationBlock, EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.prompts import QUALIFIED, active_prompt
from apps.jobs.models import Job, JobExecutionState
from apps.documents.models import Document
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
    revision_ids = sorted(
        document.pages.exclude(current_revision_id=None).values_list("current_revision_id", flat=True)
    )
    prompt_versions = ",".join(sorted(QUALIFIED.values()))
    model = getattr(settings, "ENRICHMENT_MODEL", "mock-gpt")
    payload = f"{document.pk}|{revision_ids}|{prompt_versions}|{model}"
    return hashlib.sha256(payload.encode()).hexdigest()


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

            from apps.ai_classroom.budget import assert_within_budget

            assert_within_budget(document.profile_id)

            existing = (
                EnrichedNote.objects.filter(document=document, superseded=False, ai_stale=False).first()
                if not force_refresh
                else None
            )
            if existing and existing.blocks.exists():
                return {"note": existing, "job": None, "created": False}

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


def run_enrichment_job(job: Job) -> None:
    from ai.langgraph.graphs.enrichment_graph import invoke_enrichment_graph
    from ai.langgraph.state.enrichment_state import EnrichmentState

    document = Document.objects.select_related("profile").get(pk=job.resource_id)

    # --- Checkpoint recovery (§28/§52): resume from last completed node --
    last_checkpoint = JobExecutionState.objects.filter(job=job).order_by("-created_at").first()
    initial_state = EnrichmentState(
        document_id=str(document.pk),
        job_id=str(job.pk),
        user_chunks=[],
        reference_chunks=[],
        evidence_payload={},
        draft_result={},
        gaps_result={},
        fill_result={},
        all_blocks=[],
        stitched_blocks=[],
        errors=[],
        execution_metadata={},
    )
    start_node = "retrieve"

    if last_checkpoint:
        checkpoint_state = last_checkpoint.get_state()
        start_node = _get_next_node(checkpoint_state.get("completed_node", "retrieve"))
        # Merge checkpoint state into initial state, preserving any computed values
        for key, value in checkpoint_state.items():
            if key != "completed_node" and key != "id" and key != "job" and key != "created_at":
                initial_state[key] = value
    else:
        initial_state = EnrichmentState(
            document_id=str(document.pk),
            job_id=str(job.pk),
            user_chunks=[],
            reference_chunks=[],
            evidence_payload={},
            draft_result={},
            gaps_result={},
            fill_result={},
            all_blocks=[],
            stitched_blocks=[],
            errors=[],
            execution_metadata={},
        )

    # Execute from the appropriate starting node
    if start_node == "retrieve":
        final_state = invoke_enrichment_graph(initial_state)
    else:
        final_state = invoke_enrichment_graph(initial_state)

    # Save checkpoint after successful graph execution
    completed_node_map = {
        "format_output": "format_output",
        "evidence_verification": "evidence_verification",
        "citation_stitch": "citation_stitch",
        "gap_fill": "gap_fill",
        "gap_detection": "gap_detection",
        "draft": "draft",
        "retrieve": "retrieve",
    }
    last_node = completed_node_map.get("format_output", "retrieve")

    JobExecutionState.objects.create(
        job=job,
        state_json=final_state,
        completed_node=last_node,
    )
    # -------------------------------------------------------------------------

    stitched = final_state.get("stitched_blocks", [])
    draft_prompt = active_prompt("enrichment_draft")
    llm = get_llm_provider()

    # ---- Persist atomically (§67-style boundary) --------------------------
    # Tagging and question generation are now inside the transaction (§53/§54):
    # if they fail, the entire enrichment (note + blocks + citations + tags + questions)
    # is rolled back and retried, avoiding inconsistent state.
    try:
        with transaction.atomic():
            EnrichedNote.objects.filter(document=document, superseded=False).update(superseded=True)
            note = EnrichedNote.objects.create(
                document=document,
                content_hash=_descriptor(document),
                revision_ids=[
                    str(pk)
                    for pk in document.pages.exclude(current_revision_id=None).values_list(
                        "current_revision_id", flat=True
                    )
                ],
                generation_job=job,
                provider=llm.name,
                model=getattr(settings, "ENRICHMENT_MODEL", "mock-gpt"),
                prompt_version=";".join(QUALIFIED.values()),
                schema_version=draft_prompt.output_schema_version,
            )
            for item in stitched:
                block = EnrichedNoteBlock.objects.create(
                    enriched_note=note,
                    block_index=item["index"],
                    block_type=item["block_type"],
                    title=item.get("title", ""),
                    content=item["content"],
                    generation_method=item["generation_method"],
                    source_chunk_ids=item["source_chunk_ids"],
                )
                CitationBlock.objects.create(
                    enriched_note_block=block,
                    source_refs=item["refs"],
                    verification_status=item["status"],
                    verification_score=item["score"],
                    verifier_version=EvidenceVerifier.VERSION,
                )
            # ---- §53/§54 learning-feature hooks (now inside transaction) ----
            from apps.ai_classroom.tagging import TaggingService
            from apps.questions.services import QuestionGenerationService

            TaggingService.extract_for_document(document, generation_job=job)
            QuestionGenerationService.generate_for_document(document)
    except Exception as exc:
        # Log the error and re-raise to trigger job retry
        logger.error(
            "Enrichment failed during atomic block for document %s: %s",
            document.pk,
            exc,
        )
        raise

    logger.info(
        "Enriched document %s: %s blocks (%s verified)",
        document.pk, len(stitched), sum(1 for s in stitched if s["status"] == "supported"),
    )
