"""Revision-aware chunking, incremental indexing, and hybrid retrieval
(architecture §8, §10, §14).

Chunking: page-aware greedy packing of the document's current-revision
lines into word-bounded chunks; a carried overlap gives surrounding
context so page boundaries do not unnecessarily break concepts (§10).

Indexing is INCREMENTAL and revision-aware:
- chunks whose content_hash already exists for the document are kept
  (never re-embedded);
- chunks superseded by newer content are marked stale=true (retained,
  excluded from retrieval);
- only new/changed chunks are embedded.

Retrieval: dense pgvector cosine + PostgreSQL full-text rank fused with
Reciprocal Rank Fusion; profile/subject scoping enforced at SQL level;
reference-book chunks included only when their book is READY (§15).
"""
import hashlib
import json
import logging

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction

from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from apps.jobs.models import Job
from apps.retrieval.models import NoteChunk

logger = logging.getLogger(__name__)


def chunker_version() -> str:
    return getattr(settings, "CHUNKER_VERSION", "v1")


def _chunk_words() -> int:
    return int(getattr(settings, "CHUNK_WORDS", 120))


def _overlap_words() -> int:
    return int(getattr(settings, "CHUNK_OVERLAP_WORDS", 30))


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_chunks_for_page(page: DocumentPage) -> list[dict]:
    """Deterministic page-bounded chunks over the page's current revision. Chunks NEVER cross page boundaries."""
    if not page.current_revision_id:
        return []
    try:
        revision = DocumentPageRevision.objects.get(pk=page.current_revision_id)
    except DocumentPageRevision.DoesNotExist:
        return []

    lines = list(revision.lines.order_by("line_index"))
    if not lines:
        return []

    units: list[str] = [line.text for line in lines]
    target = max(20, _chunk_words())
    overlap = min(_overlap_words(), target // 2)

    chunks: list[dict] = []
    body: list[str] = []
    carry: list[str] = []

    def flush():
        nonlocal body, carry
        if not body:
            return
        all_units = carry + body
        content = "\n".join(all_units)
        idx = len(chunks)
        chunks.append(
            {
                "content": content,
                "content_hash": _content_hash(content),
                "page_start": page.page_number,
                "page_end": page.page_number,
                "revision_ids": [str(revision.pk)],
                "chunk_index": page.page_number * 10000 + idx,
            }
        )
        remaining = overlap
        taken_lines: list[str] = []
        for t in reversed(all_units):
            taken_lines.insert(0, t)
            remaining -= len(t.split())
            if remaining <= 0 or len(taken_lines) >= 3:
                break
        carry = taken_lines
        body = []

    for text in units:
        words_in_line = len(text.split())
        pending = sum(len(t.split()) for t in body)
        if body and pending + words_in_line > target:
            flush()
        body.append(text)
    flush()
    return chunks


def build_chunks(document: Document) -> list[dict]:
    """Deterministic page-bounded chunks across approved, non-ignored pages. Pure function."""
    pages = list(document.pages.filter(is_approved=True, is_ignored=False).order_by("page_number"))
    chunks: list[dict] = []
    for page in pages:
        chunks.extend(build_chunks_for_page(page))
    return chunks


def combined_revision_hash(document: Document) -> str:
    hashes = list(
        DocumentPageRevision.objects.filter(
            id__in=document.pages.exclude(current_revision_id=None).values_list("current_revision_id", flat=True)
        )
        .order_by("id")
        .values_list("content_hash", flat=True)
    )
    return hashlib.sha256("|".join(hashes).encode()).hexdigest()


def index_key(document: Document) -> str:
    return (
        f"index:{document.pk}:{combined_revision_hash(document)[:32]}:"
        f"{chunker_version()}:{_model_version()}"
    )


def _model_version() -> str:
    from providers.registry import embedding_model_version

    return embedding_model_version()


def enqueue_page_index_job(page: DocumentPage) -> tuple[Job, bool]:
    from apps.jobs.services import dispatch_job, get_or_create_job

    idempotency_key = (
        f"index_page:{page.pk}:{page.current_revision_id}:{page.index_epoch}:{_model_version()}"
    )
    job, created = get_or_create_job(
        job_type="index_page",
        resource_type="document_page",
        resource_id=str(page.pk),
        profile_id=page.document.profile_id,
        revision_id=page.current_revision_id,
        idempotency_key=idempotency_key,
    )
    if created or job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
        if not created:
            Job.objects.filter(pk=job.pk).update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
            job.refresh_from_db()
        dispatch_job(job)
        job.refresh_from_db()
    return job, created


def run_page_index_job(job: Job) -> None:
    try:
        page = DocumentPage.objects.select_related("document", "document__profile").get(pk=job.resource_id)
    except DocumentPage.DoesNotExist:
        logger.info("Page index job %s page %s no longer exists; skipping.", job.pk, job.resource_id)
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status",))
        return
    stats = index_page(page)
    logger.info(
        "Indexed page %s: kept=%s staled=%s created=%s embedded=%s",
        page.pk,
        stats.get("kept", 0),
        stats.get("staled", 0),
        stats.get("created", 0),
        stats.get("embedded", 0),
    )


def index_page(page: DocumentPage) -> dict:
    """Incremental diff-based indexing for a single page. Safe to run repeatedly."""
    from providers.registry import get_embedding_provider, embedding_model_version

    document = page.document
    stats = {"kept": 0, "staled": 0, "deleted": 0, "created": 0, "embedded": 0}

    # If page is not approved or is ignored, deactivate covering chunks (unless reference document)
    is_reference = document.source_type == Document.SourceType.REFERENCE or document.profile_id is None
    if not is_reference and (not page.is_approved or page.is_ignored):
        staled = NoteChunk.objects.filter(
            document=document,
            page_start__lte=page.page_number,
            page_end__gte=page.page_number,
            stale=False,
        ).update(stale=True)
        stats["staled"] = staled
        if page.indexed_text_hash:
            page.indexed_text_hash = ""
            page.save(update_fields=("indexed_text_hash",))
        return stats

    if not page.current_revision_id:
        return stats

    revision = DocumentPageRevision.objects.filter(pk=page.current_revision_id).first()
    if not revision:
        return stats

    if not revision.text_hash:
        text_content = "\n".join(l.text for l in revision.lines.order_by("line_index"))
        revision.text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        revision.save(update_fields=("text_hash",))

    desired = build_chunks_for_page(page)
    provider = get_embedding_provider()
    model_version = embedding_model_version()
    current_model = provider.name
    keep_hashes = {c["content_hash"] for c in desired}

    # Idempotent skip: if already indexed with matching text_hash and active chunks exist
    if page.indexed_text_hash and page.indexed_text_hash == revision.text_hash:
        active_chunks = NoteChunk.objects.filter(
            document=document,
            page_start__lte=page.page_number,
            page_end__gte=page.page_number,
            stale=False,
            embedding_model=current_model,
            embedding_version=model_version,
        )
        if active_chunks.count() == len(desired):
            return stats

    with transaction.atomic():
        chunks_needing_embed = []
        for c in desired:
            obj, obj_created = NoteChunk.objects.get_or_create(
                revision_id=revision.pk,
                content_hash=c["content_hash"],
                chunk_index=c["chunk_index"],
                defaults={
                    "document": document,
                    "profile": document.profile,
                    "subject": document.subject,
                    "revision_ids": c["revision_ids"],
                    "page_start": c["page_start"],
                    "page_end": c["page_end"],
                    "content": c["content"],
                    "source_type": document.source_type,
                    "reference_book": getattr(document, "reference_book", None),
                    "stale": False,
                },
            )
            if obj_created:
                stats["created"] += 1
                chunks_needing_embed.append(obj)
            else:
                stats["kept"] += 1
                needs_update = False
                update_fields = []
                if obj.stale:
                    obj.stale = False
                    needs_update = True
                    update_fields.append("stale")
                if (
                    obj.embedding is None
                    or obj.embedding_model != current_model
                    or obj.embedding_version != model_version
                ):
                    chunks_needing_embed.append(obj)
                elif needs_update:
                    obj.save(update_fields=update_fields)

        # Deactivate any covering chunks on this page that are not in the desired set
        staled = NoteChunk.objects.filter(
            document=document,
            page_start__lte=page.page_number,
            page_end__gte=page.page_number,
            stale=False,
        ).exclude(content_hash__in=keep_hashes).update(stale=True)
        stats["staled"] = staled

        # Embed chunks that need embeddings
        if chunks_needing_embed:
            texts = [c.content for c in chunks_needing_embed]
            try:
                vectors = provider.embed(texts, model_version=model_version)
            except Exception as exc:
                logger.error("Embedding failed for page %s: %s", page.pk, exc)
                vectors = [None] * len(chunks_needing_embed)

            for c_obj, vec in zip(chunks_needing_embed, vectors):
                if vec is not None:
                    c_obj.embedding = vec
                    c_obj.embedding_model = current_model
                    c_obj.embedding_version = model_version
                    c_obj.stale = False
                    stats["embedded"] += 1
                    c_obj.save(update_fields=("embedding", "embedding_model", "embedding_version", "stale"))

        # Mark page indexed with this revision's text_hash
        page.indexed_text_hash = revision.text_hash
        page.save(update_fields=("indexed_text_hash",))

    return stats


def enqueue_index_job(document: Document) -> tuple[Job, bool]:
    from apps.jobs.services import dispatch_job, get_or_create_job

    job, created = get_or_create_job(
        job_type="index",
        resource_type="document",
        resource_id=str(document.pk),
        profile_id=document.profile_id,
        idempotency_key=index_key(document),
    )
    if created or job.status in (Job.Status.FAILED_RETRYABLE, Job.Status.FAILED_DEAD_LETTER):
        if not created:
            Job.objects.filter(pk=job.pk).update(status=Job.Status.QUEUED, next_retry_at=None, last_error="")
            job.refresh_from_db()
        dispatch_job(job)
        # eager execution may have finished already; never hand back stale state
        job.refresh_from_db()
    return job, created


def run_index_job(job: Job) -> None:
    try:
        document = Document.objects.select_related("profile").get(pk=job.resource_id)
    except Document.DoesNotExist:
        logger.info("Index job %s document %s no longer exists (deleted); skipping.", job.pk, job.resource_id)
        job.status = Job.Status.CANCELLED
        job.save(update_fields=("status",))
        return
    stats = index_document(document)
    logger.info(
        "Indexed document %s: kept=%s stale=%s created=%s embedded=%s",
        document.pk, stats["kept"], stats["staled"], stats["created"], stats["embedded"],
    )


def index_document(document: Document) -> dict:
    """Incremental diff-based indexing across all approved, non-ignored pages."""
    is_reference = document.source_type == Document.SourceType.REFERENCE or document.profile_id is None
    if is_reference:
        pages = list(document.pages.filter(is_ignored=False).order_by("page_number"))
    else:
        pages = list(document.pages.filter(is_approved=True, is_ignored=False).order_by("page_number"))
    total_stats = {"kept": 0, "deleted": 0, "created": 0, "embedded": 0, "staled": 0}
    for page in pages:
        st = index_page(page)
        for k in ("kept", "created", "embedded", "staled"):
            total_stats[k] += st.get(k, 0)

    # populate tsvector for any chunk missing it (PostgreSQL only; SQLite
    # has no to_tsvector and its retrieval leg uses icontains instead)
    from django.db import connection

    if connection.vendor == "postgresql":
        missing_ts = NoteChunk.objects.filter(document=document, tsvector_content__isnull=True)
        for chunk in missing_ts.iterator():
            NoteChunk.objects.filter(pk=chunk.pk).update(
                tsvector_content=SearchVector("content", config="english")
            )

    return total_stats
