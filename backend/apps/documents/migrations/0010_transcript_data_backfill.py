# Generated for StudyAI: PR 1 Step 1 - Transcript Data Backfill
import hashlib
import logging
import uuid

from django.db import migrations, models
from django.utils import timezone

logger = logging.getLogger(__name__)


def backfill_transcript_data(apps, schema_editor):
    DocumentPage = apps.get_model("documents", "DocumentPage")
    DocumentPageRevision = apps.get_model("documents", "DocumentPageRevision")
    DocumentLine = apps.get_model("documents", "DocumentLine")
    try:
        NoteChunk = apps.get_model("retrieval", "NoteChunk")
    except LookupError:
        NoteChunk = None
    try:
        EnrichedNote = apps.get_model("ai_classroom", "EnrichedNote")
    except LookupError:
        EnrichedNote = None

    # 1. Backfill revision_type
    user_edits = DocumentPageRevision.objects.filter(
        models.Q(content_snapshot__origin="user_edit") | models.Q(edited_by__isnull=False)
    ).update(revision_type="user_edit")
    ocr_edits = DocumentPageRevision.objects.filter(revision_type="").update(revision_type="ocr")
    logger.info("Backfilled revision_type: %d user_edit, %d ocr", user_edits, ocr_edits)

    # 2. Backfill lineage_id and original_text on DocumentLine
    lines_qs = DocumentLine.objects.filter(lineage_id__isnull=True).iterator(chunk_size=500)
    batch = []
    for line in lines_qs:
        line.lineage_id = uuid.uuid4()
        if not line.original_text:
            line.original_text = line.text or ""
        batch.append(line)
        if len(batch) >= 500:
            DocumentLine.objects.bulk_update(batch, ["lineage_id", "original_text"])
            batch = []
    if batch:
        DocumentLine.objects.bulk_update(batch, ["lineage_id", "original_text"])

    # 3. Backfill text_hash on DocumentPageRevision
    for rev in DocumentPageRevision.objects.filter(text_hash="").iterator(chunk_size=200):
        lines_text = list(
            DocumentLine.objects.filter(page_revision=rev)
            .order_by("line_index")
            .values_list("text", flat=True)
        )
        rev.text_hash = hashlib.sha256("\n".join(lines_text).encode()).hexdigest()
        rev.save(update_fields=["text_hash"])

    # 4. Backfill legacy page approvals safely using line heuristics (NO MinIO calls)
    for page in DocumentPage.objects.filter(ocr_status="completed").iterator(chunk_size=100):
        # If already approved or has a user edit, stay approved
        has_user_edit = DocumentPageRevision.objects.filter(
            id=page.current_revision_id, revision_type="user_edit"
        ).exists()
        if page.is_approved or has_user_edit:
            page.is_approved = True
            page.review_status = "approved"
            if not page.approved_at:
                page.approved_at = timezone.now()
            page.save(update_fields=["is_approved", "review_status", "approved_at"])
            continue

        # Evaluate line-based rules on current revision
        if not page.current_revision_id:
            page.is_approved = False
            page.review_status = "needs_review"
            page.save(update_fields=["is_approved", "review_status"])
            continue

        lines = list(
            DocumentLine.objects.filter(page_revision_id=page.current_revision_id)
            .order_by("line_index")
            .values("text", "confidence_score")
        )
        total_lines = len(lines)
        has_anomaly = False

        if total_lines == 0:
            has_anomaly = True
        else:
            illegible_count = sum(1 for l in lines if "[illegible]" in (l["text"] or "").lower())
            if (illegible_count / total_lines) > 0.15:
                has_anomaly = True

            uncertain_count = sum(
                1 for l in lines if l["confidence_score"] is not None and l["confidence_score"] < 0.80
            )
            if (uncertain_count / total_lines) > 0.30:
                has_anomaly = True

            # Repetition check: 4 or more identical consecutive lines
            rep_count = 1
            for i in range(1, total_lines):
                if lines[i]["text"] and lines[i]["text"] == lines[i - 1]["text"]:
                    rep_count += 1
                    if rep_count >= 4:
                        has_anomaly = True
                        break
                else:
                    rep_count = 1

        if has_anomaly:
            page.is_approved = False
            page.review_status = "needs_review"
        else:
            page.is_approved = True
            page.review_status = "approved"
            if not page.approved_at:
                page.approved_at = timezone.now()

        page.save(update_fields=["is_approved", "review_status", "approved_at"])

    # 5. Backfill indexed_text_hash for already-indexed approved pages
    if NoteChunk is not None:
        for page in DocumentPage.objects.filter(is_approved=True, indexed_text_hash="").iterator(chunk_size=100):
            has_active_chunks = NoteChunk.objects.filter(
                document_id=page.document_id,
                page_start__lte=page.page_number,
                page_end__gte=page.page_number,
                stale=False,
            ).exists()
            if has_active_chunks and page.current_revision_id:
                rev = DocumentPageRevision.objects.filter(id=page.current_revision_id).first()
                if rev and rev.text_hash:
                    page.indexed_text_hash = rev.text_hash
                    page.save(update_fields=["indexed_text_hash"])

    # 6. Recompute v2: descriptor hash inline for existing active EnrichedNote instances
    if EnrichedNote is not None:
        for note in EnrichedNote.objects.filter(superseded=False).iterator(chunk_size=50):
            if note.content_hash.startswith("v2:"):
                continue
            approved_pages = list(
                DocumentPage.objects.filter(
                    document_id=note.document_id, is_approved=True, is_ignored=False
                ).order_by("page_number")
            )
            if not approved_pages:
                continue
            tuples = []
            for p in approved_pages:
                if not p.current_revision_id:
                    continue
                for line in DocumentLine.objects.filter(page_revision_id=p.current_revision_id).order_by("line_index"):
                    tuples.append(f"{p.page_number}:{line.line_index}:{line.text}")
            if tuples:
                note.content_hash = "v2:" + hashlib.sha256("|".join(tuples).encode()).hexdigest()[:61]
                note.save(update_fields=["content_hash"])

    # 7. Defensive check for (page, revision_number) duplicates
    dups = (
        DocumentPageRevision.objects.values("page_id", "revision_number")
        .annotate(cnt=models.Count("id"))
        .filter(cnt__gt=1)
    )
    dup_count = dups.count()
    if dup_count > 0:
        logger.warning("Defensive check found %d duplicate (page, revision_number) rows", dup_count)
    else:
        logger.info("Defensive check verified: 0 duplicate (page, revision_number) rows found.")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("documents", "0009_transcript_schema_nullable"),
        ("ai_classroom", "0004_enrichednote_empty_reason"),
        ("retrieval", "0004_qwen3_embeddings_1024"),
    ]

    operations = [
        migrations.RunPython(backfill_transcript_data, migrations.RunPython.noop),
    ]
