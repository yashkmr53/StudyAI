"""Load and Gate Node for Topic-Based Note Enrichment (PR 2).

Loads approved transcript lines, verifies document readiness, applies the
academic content gate, captures inputs at job start, and checks for up-to-date notes.
"""
import hashlib
import json
import logging
from typing import Any, Dict

from django.conf import settings

from ai.langgraph.state.topic_enrichment_state import TopicEnrichmentState
from apps.ai_classroom.content_gate import validate_text_academic_content
from apps.ai_classroom.models import EnrichedNote
from apps.ai_classroom.services import _descriptor
from apps.documents.models import Document
from apps.jobs.models import Job

logger = logging.getLogger(__name__)


def load_and_gate_node(state: TopicEnrichmentState) -> Dict[str, Any]:
    """Execute load and gate stage (§3.1, §3.7.3)."""
    document_id = state.get("document_id")
    job_id = state.get("job_id")
    force_include_line_ids = state.get("force_include_line_ids") or []

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return {
            "is_ready": False,
            "outcome": "not_ready",
            "error_code": "DOCUMENT_NOT_FOUND",
        }

    # 1. Verify PR 1 Readiness: all pages must be reviewed (approved or ignored)
    # and at least one page must be approved and non-ignored.
    has_unapproved = document.pages.filter(is_approved=False, is_ignored=False).exists()
    has_approved = document.pages.filter(is_approved=True, is_ignored=False).exists()

    if has_unapproved or not has_approved:
        logger.info("Document %s is not ready for enrichment", document_id)
        return {
            "is_ready": False,
            "outcome": "not_ready",
            "error_code": "NOT_READY_FOR_ENRICHMENT",
        }

    # 2. Extract approved lines
    approved_pages = list(
        document.pages.filter(is_approved=True, is_ignored=False)
        .prefetch_related("current_revision__lines")
        .order_by("page_number")
    )

    approved_lines = []
    text_chunks = []
    for page in approved_pages:
        rev = page.current_revision
        if not rev:
            continue
        page_lines = []
        for line in rev.lines.order_by("line_index"):
            approved_lines.append({
                "id": str(line.id),
                "lineage_id": str(line.lineage_id),
                "text": line.text,
                "line_index": line.line_index,
                "page_number": page.page_number,
                "is_heading": line.is_heading,
                "confidence_score": line.confidence_score,
            })
            page_lines.append(line.text)
        if page_lines:
            text_chunks.append("\n".join(page_lines))

    full_text = "\n\n".join(text_chunks).strip()

    # 3. Validate Academic Content Gate (§3.1)
    is_valid, reason, _ = validate_text_academic_content(full_text)
    if not is_valid:
        logger.info("Document %s rejected by academic content gate: %s", document_id, reason)
        return {
            "is_ready": False,
            "outcome": "insufficient_content",
            "error_code": "INSUFFICIENT_CONTENT",
            "approved_lines": approved_lines,
        }

    # 4. Capture Inputs at Job Start (§3.7.3, §3.3)
    start_hash = _descriptor(document)
    norm_force_ids = sorted([str(x) for x in force_include_line_ids])
    force_include_hash = (
        hashlib.sha256(json.dumps(norm_force_ids).encode("utf-8")).hexdigest()[:16]
        if norm_force_ids
        else ""
    )
    base_version = getattr(settings, "PROMPT_VERSION", "topic_enrichment:v1")
    from apps.references.services import reference_library_hash
    ref_hash = reference_library_hash(document.subject)
    settings_version = f"{base_version}:{ref_hash}"

    # Record captured inputs in Job.metadata
    if job_id:
        try:
            job = Job.objects.get(pk=job_id)
            job.metadata.update({
                "start_hash": start_hash,
                "force_include_hash": force_include_hash,
                "force_include_line_ids": norm_force_ids,
                "settings_version": settings_version,
                "reference_snapshot_hash": ref_hash,
            })
            job.save(update_fields=("metadata",))
        except Job.DoesNotExist:
            pass

    # 5. Early-Exit No-Op Check (§3.7.3)
    # If active, fresh note with identical inputs already exists, exit early as already_up_to_date
    # Skip early exit if this job was explicitly dispatched as a refresh or forced rerun
    is_forced_rerun = False
    if job_id:
        try:
            j_obj = Job.objects.filter(pk=job_id).first()
            if j_obj and (
                j_obj.metadata.get("force_rerun")
                or j_obj.metadata.get("force_refresh")
                or ":refresh:" in (j_obj.idempotency_key or "")
            ):
                is_forced_rerun = True
        except Exception:
            pass

    if not is_forced_rerun:
        active_note = EnrichedNote.objects.filter(
            document=document,
            superseded=False,
            ai_stale=False,
            content_hash=start_hash,
            force_include_hash=force_include_hash,
            settings_version=settings_version,
        ).first()

        if active_note is not None:
            logger.info("Document %s already has up-to-date active note %s", document_id, active_note.id)
            return {
                "is_ready": False,
                "outcome": "already_up_to_date",
                "error_code": "",
                "start_hash": start_hash,
                "force_include_hash": force_include_hash,
                "settings_version": settings_version,
                "reference_snapshot_hash": ref_hash,
                "approved_lines": approved_lines,
            }

    return {
        "is_ready": True,
        "start_hash": start_hash,
        "force_include_hash": force_include_hash,
        "settings_version": settings_version,
        "reference_snapshot_hash": ref_hash,
        "approved_lines": approved_lines,
        "force_include_line_ids": norm_force_ids,
    }
