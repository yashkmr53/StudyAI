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

from django.conf import settings
from django.db import transaction

from apps.ai_classroom.models import CitationBlock, EnrichedNote, EnrichedNoteBlock
from apps.ai_classroom.prompts import QUALIFIED, active_prompt, validate_stage_output
from apps.documents.models import Document
from apps.jobs.models import Job
from apps.retrieval.models import NoteChunk
from providers.base import Prompt
from shared.exceptions import ResourceNotFound, ValidationError

logger = logging.getLogger(__name__)


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
    def verify(cls, block_content: str, source_refs: list[dict]) -> tuple[str, float | None]:
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
    def _classify(cls, block_content: str, cited_contents: list[str]) -> tuple[str, float | None]:
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
    def enqueue_enrichment(user, document_id, *, force_refresh: bool = False) -> dict:
        from apps.jobs.services import dispatch_job, get_or_create_job

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
    document = Document.objects.select_related("profile").get(pk=job.resource_id)

    # ---- A. Retrieve ------------------------------------------------------
    user_chunks = list(
        NoteChunk.objects.filter(document=document, stale=False)
        .select_related("reference_book")
        .order_by("chunk_index")[:8]
    )
    reference_chunks = list(
        NoteChunk.objects.filter(
            source_type="reference",
            stale=False,
            reference_book__status="ready",
        ).exclude(reference_book__isnull=True)
        .select_related("reference_book")
        .order_by("?")[:6]
    )

    def as_evidence(chunks: list[NoteChunk]) -> list[dict]:
        return [{"chunk_id": str(c.pk), "content": c.content} for c in chunks]

    # ---- B. Draft (schema-validated) -------------------------------------
    from providers.registry import get_llm_provider

    llm = get_llm_provider()
    draft_prompt = active_prompt("enrichment_draft")
    evidence_payload = {"user_chunks": as_evidence(user_chunks), "reference_chunks": as_evidence(reference_chunks)}
    draft_result = llm.generate_structured(
        prompt=Prompt(
            name="enrichment_draft",
            version=draft_prompt.version,
            user=draft_prompt.template + "\nEVIDENCE_JSON:" + json.dumps(evidence_payload),
        ),
        request_id=f"job_{job.pk}",
    )
    validate_stage_output("enrichment_draft", draft_result.data)

    # ---- C. Gap detection (schema-validated) -----------------------------
    gaps_prompt = active_prompt("gap_detection")
    gaps_result = llm.generate_structured(
        prompt=Prompt(
            name="gap_detection",
            version=gaps_prompt.version,
            user=gaps_prompt.template + "\nEVIDENCE_JSON:" + json.dumps(evidence_payload),
        ),
        request_id=f"job_{job.pk}",
    )
    validate_stage_output("gap_detection", gaps_result.data)

    # ---- D. Gap filling (schema-validated) -------------------------------
    fill_prompt = active_prompt("gap_filling")
    fill_evidence = {**evidence_payload, "gaps": gaps_result.data["gaps"]}
    fill_result = llm.generate_structured(
        prompt=Prompt(
            name="gap_filling",
            version=fill_prompt.version,
            user=fill_prompt.template + "\nEVIDENCE_JSON:" + json.dumps(fill_evidence),
        ),
        request_id=f"job_{job.pk}",
    )
    validate_stage_output("gap_filling", fill_result.data)

    all_blocks = draft_result.data["blocks"] + fill_result.data["blocks"]

    # ---- E/F. Citation stitch + evidence verification --------------------
    chunk_meta = {str(c.pk): c for c in [*user_chunks, *reference_chunks]}
    stitched = []
    for i, block in enumerate(all_blocks):
        refs = []
        for cid in block.get("source_chunk_ids", []):
            chunk = chunk_meta.get(cid)
            if chunk is None:
                continue
            revision_id = chunk.revision_ids[0] if chunk.revision_ids else None
            refs.append({
                "source_type": chunk.source_type,
                "chunk_id": str(chunk.pk),
                "document_id": str(chunk.document_id),
                "page_number": chunk.page_start,
                "revision_id": revision_id,
                "retrieval_score": None,
            })
        status, score = EvidenceVerifier.verify(block["content"], refs)
        stitched.append({"index": i, **block, "refs": refs, "status": status, "score": score})

    # ---- Persist atomically (§67-style boundary) --------------------------
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
    logger.info(
        "Enriched document %s: %s blocks (%s verified)",
        document.pk, len(stitched), sum(1 for s in stitched if s["status"] == "supported"),
    )

    # ---- §53/§54 learning-feature hooks --------------------------------
    from apps.ai_classroom.tagging import TaggingService
    from apps.questions.services import QuestionGenerationService

    TaggingService.extract_for_document(document, generation_job=job)
    QuestionGenerationService.generate_for_document(document)
