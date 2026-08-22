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

from apps.documents.models import Document, DocumentPageRevision
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


def build_chunks(document: Document) -> list[dict]:
    """Deterministic page-aware chunks over CURRENT revisions. Pure function."""
    pages = list(document.pages.order_by("page_number"))
    units: list[tuple[int, str]] = []
    revision_ids: list[str] = []
    for page in pages:
        if not page.current_revision_id:
            continue  # pages without revisions contribute nothing yet
        revision = DocumentPageRevision.objects.get(pk=page.current_revision_id)
        revision_ids.append(str(revision.pk))
        for line in revision.lines.order_by("line_index"):
            units.append((page.page_number, line.text))

    target = max(20, _chunk_words())
    overlap = min(_overlap_words(), target // 2)

    chunks: list[dict] = []
    body: list[tuple[int, str]] = []
    carry: list[tuple[int, str]] = []

    def flush():
        nonlocal body, carry
        if not body:
            return
        all_units = carry + body
        content = "\n".join(t for _, t in all_units)
        page_numbers = [p for p, _ in all_units]
        chunks.append(
            {
                "content": content,
                "content_hash": _content_hash(content),
                "page_start": min(page_numbers),
                "page_end": max(page_numbers),
                "revision_ids": sorted(set(revision_ids)),
                "chunk_index": len(chunks),
            }
        )
        # carry tail as context window into the next chunk (§10)
        flat_words: list[tuple[int, str]] = []
        for p, t in all_units[-6:]:
            for w in t.split():
                flat_words.append((p, w))
        carry_units: list[tuple[int, str]] = []
        remaining = overlap
        taken_lines: list[tuple[int, str]] = []
        for p, t in reversed(all_units):
            taken_lines.insert(0, (p, t))
            remaining -= len(t.split())
            if remaining <= 0 or len(taken_lines) >= 3:
                break
        carry_units = taken_lines
        body = []
        carry = carry_units

    for page_number, text in units:
        words_in_line = len(text.split())
        pending = sum(len(t.split()) for _, t in body)
        if body and pending + words_in_line > target:
            flush()
        body.append((page_number, text))
    flush()
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
    document = Document.objects.select_related("profile").get(pk=job.resource_id)
    stats = index_document(document)
    logger.info(
        "Indexed document %s: kept=%s stale=%s created=%s embedded=%s",
        document.pk, stats["kept"], stats["staled"], stats["created"], stats["embedded"],
    )


def index_document(document: Document) -> dict:
    """Incremental diff-based indexing. Safe to run repeatedly."""
    from providers.registry import get_embedding_provider, embedding_model_version

    desired = build_chunks(document)
    desired_hashes = {c["content_hash"] for c in desired}

    existing_active = NoteChunk.objects.filter(document=document, stale=False)
    keep_hashes = set(existing_active.filter(content_hash__in=desired_hashes).values_list("content_hash", flat=True))
    superseded_ids = list(
        existing_active.exclude(content_hash__in=keep_hashes).values_list("pk", flat=True)
    )
    staled = len(superseded_ids)
    if superseded_ids:
        NoteChunk.objects.filter(pk__in=superseded_ids).update(stale=True)
        # §17/§54: questions tied to superseded chunks become stale (never deleted)
        from apps.questions.models import Question

        Question.objects.filter(source_chunk_id__in=superseded_ids, stale=False).update(stale=True)

    new_chunks = [c for c in desired if c["content_hash"] not in keep_hashes]
    created_rows: list[NoteChunk] = []
    with transaction.atomic():
        for c in new_chunks:
            obj, obj_created = NoteChunk.objects.get_or_create(
                revision_id=c["revision_ids"][0] if c["revision_ids"] else "00000000-0000-0000-0000-000000000000",
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
                },
            )
            if obj_created:
                created_rows.append(obj)
            elif obj.stale:  # previously-staled hash re-appears → resurrect without re-embedding
                obj.stale = False
                obj.save(update_fields=("stale",))

    provider = get_embedding_provider()
    model_version = embedding_model_version()

    # Embed only new/changed chunks: freshly created rows + any active row
    # still missing a vector. De-duplicated by pk.
    embeddable: list[NoteChunk] = []
    seen: set = set()
    for chunk in created_rows:
        if chunk.pk not in seen:
            seen.add(chunk.pk)
            embeddable.append(chunk)
    for chunk in NoteChunk.objects.filter(document=document, stale=False, embedding__isnull=True).exclude(
        pk__in=seen
    ):
        seen.add(chunk.pk)
        embeddable.append(chunk)

    vectors = provider.embed([c.content for c in embeddable], model_version=model_version) if embeddable else []
    for chunk, vector in zip(embeddable, vectors):
        chunk.embedding = vector
        chunk.embedding_model = provider.name
        chunk.embedding_version = model_version
        chunk.save(update_fields=("embedding", "embedding_model", "embedding_version"))

    # populate tsvector for any chunk missing it (PostgreSQL only; SQLite
    # has no to_tsvector and its retrieval leg uses icontains instead)
    from django.db import connection

    if connection.vendor == "postgresql":
        missing_ts = NoteChunk.objects.filter(tsvector_content__isnull=True)
        for chunk in missing_ts.iterator():
            NoteChunk.objects.filter(pk=chunk.pk).update(
                tsvector_content=SearchVector("content", config="english")
            )

    # §21/§27: content changed → dependent AI artifacts become stale.
    from apps.ai_classroom.models import EnrichedNote

    EnrichedNote.objects.filter(document=document).update(ai_stale=True)

    return {
        "kept": len(keep_hashes),
        "staled": staled,
        "created": len(created_rows),
        "embedded": len(vectors),
    }
