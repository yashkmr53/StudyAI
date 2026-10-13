"""Reference document ingestion service (Phase 11 §4, §22).

Orchestrates:
1. Reading PDF from object storage
2. Page text extraction (with qwen3.5:4b vision OCR fallback)
3. Deterministic chunking
4. Batched embedding generation (qwen3-embedding:0.6b via Ollama GPU)
5. Idempotent ReferenceChunk + pgvector persistence
6. Updating ReferenceDocument to READY
"""
from contextlib import contextmanager
import logging
from typing import Optional

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.references.chunking import chunk_extracted_pages
from apps.references.extraction import extract_pdf_pages
from apps.references.models import ReferenceChunk, ReferenceDocument
from providers.registry import embedding_model_version, get_embedding_provider, get_object_storage
from shared.database.rls import profile_scoped_transaction

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 32


@contextmanager
def scoped_transaction(profile_id: Optional[str] = None):
    """Context manager ensuring transaction and profile RLS scope if profile_id is present."""
    if profile_id:
        with profile_scoped_transaction(profile_id):
            yield
    else:
        with transaction.atomic():
            yield


def ingest_reference_document(doc_id: str, profile_id: Optional[str] = None) -> dict:
    """Run full ingestion pipeline on a ReferenceDocument under profile RLS scope.

    Args:
        doc_id: UUID of ReferenceDocument.
        profile_id: UUID of owning Profile (for PostgreSQL RLS context).

    Returns:
        Dict with status and metrics.
    """
    # 1. Lookup document under appropriate profile context
    try:
        with scoped_transaction(profile_id):
            doc = ReferenceDocument.objects.get(pk=doc_id)
    except ReferenceDocument.DoesNotExist:
        if profile_id is None:
            logger.error("ReferenceDocument %s does not exist; skipping ingestion.", doc_id)
        else:
            logger.error(
                "ReferenceDocument %s does not exist under profile %s; skipping ingestion.",
                doc_id,
                profile_id,
            )
        return {"status": "not_found"}

    # If profile_id wasn't provided but doc has a profile (e.g. SQLite unit tests), adopt it
    if profile_id is None and doc.profile_id:
        profile_id = str(doc.profile_id)

    # Validate that document actually belongs to the scoped profile (if scoped)
    if profile_id and doc.profile_id and str(doc.profile_id) != str(profile_id):
        logger.warning(
            "Profile mismatch for ReferenceDocument %s: doc=%s vs context=%s",
            doc_id,
            doc.profile_id,
            profile_id,
        )
        return {"status": "not_found"}

    if doc.status == ReferenceDocument.Status.READY and doc.chunk_count > 0:
        logger.info("ReferenceDocument %s is already READY; skipping duplicate ingestion.", doc_id)
        return {"status": "already_ready", "chunk_count": doc.chunk_count}

    doc.status = ReferenceDocument.Status.PROCESSING
    doc.error_message = ""
    metadata = dict(doc.metadata or {})
    metadata["stage"] = "starting"
    with scoped_transaction(profile_id):
        ReferenceDocument.objects.filter(pk=doc_id).update(
            status=ReferenceDocument.Status.PROCESSING,
            error_message="",
            metadata=metadata,
            updated_at=timezone.now(),
        )

    try:
        # 1. Fetch file bytes from storage
        storage = get_object_storage()
        if not storage.exists(doc.file_path):
            raise FileNotFoundError(f"Storage object not found: {doc.file_path}")

        pdf_bytes = storage.read_bytes(doc.file_path)

        # 2. Extract pages (with OCR fallback for scanned pages)
        metadata["stage"] = "extracting_pages"
        with scoped_transaction(profile_id):
            ReferenceDocument.objects.filter(pk=doc_id).update(
                metadata=metadata,
                updated_at=timezone.now(),
            )

        pages = extract_pdf_pages(
            pdf_bytes,
            request_id=f"ref_ingest:{doc_id}",
            ocr_fallback=True,
            fail_on_ocr_error=False,
        )
        doc.page_count = len(pages)
        metadata["page_count"] = doc.page_count
        metadata["stage"] = "chunking"
        with scoped_transaction(profile_id):
            ReferenceDocument.objects.filter(pk=doc_id).update(
                page_count=doc.page_count,
                metadata=metadata,
                updated_at=timezone.now(),
            )

        # 3. Deterministic chunking
        chunks = chunk_extracted_pages(pages)
        if not chunks:
            raise ValueError("No text could be extracted or chunked from the PDF.")

        total_chunks = len(chunks)
        metadata["total_chunks"] = total_chunks
        metadata["stage"] = "embedding_and_persisting"
        metadata["embedded_chunks"] = 0

        # Clean up any stale partial chunks before persisting new batches
        with scoped_transaction(profile_id):
            ReferenceChunk.objects.filter(reference_document_id=doc_id).delete()
            ReferenceDocument.objects.filter(pk=doc_id).update(
                chunk_count=0,
                metadata=metadata,
                updated_at=timezone.now(),
            )

        # 4. Batched embedding generation & bounded persistence with canonical qwen3-embedding:0.6b
        provider = get_embedding_provider()
        model_version = embedding_model_version()

        persisted_count = 0
        for i in range(0, total_chunks, EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            vectors = provider.embed(texts, model_version=model_version)

            chunk_rows = [
                ReferenceChunk(
                    reference_document_id=doc_id,
                    chunk_index=c["chunk_index"],
                    text=c["text"],
                    content_hash=c["content_hash"],
                    embedding=vec,
                    embedding_model=provider.name,
                    embedding_version=model_version,
                    page_number=c["page_number"],
                    chapter=c["chapter"],
                    section=c["section"],
                    metadata=c["metadata"],
                )
                for c, vec in zip(batch, vectors)
            ]

            with scoped_transaction(profile_id):
                ReferenceChunk.objects.bulk_create(chunk_rows)
                persisted_count += len(chunk_rows)

                # Periodically update progress milestone
                if persisted_count % 64 == 0 or persisted_count == total_chunks:
                    metadata["embedded_chunks"] = persisted_count
                    ReferenceDocument.objects.filter(pk=doc_id).update(
                        chunk_count=persisted_count,
                        metadata=metadata,
                        updated_at=timezone.now(),
                    )

        # 5. Populate full-text tsvector on PostgreSQL in a single set-based query
        with scoped_transaction(profile_id):
            if connection.vendor == "postgresql":
                from django.contrib.postgres.search import SearchVector
                ReferenceChunk.objects.filter(
                    reference_document_id=doc_id,
                    tsvector_content__isnull=True,
                ).update(tsvector_content=SearchVector("text", config="english"))

            # 6. Mark READY atomically
            doc.chunk_count = total_chunks
            doc.status = ReferenceDocument.Status.READY
            metadata["stage"] = "ready"
            metadata["embedded_chunks"] = total_chunks
            ReferenceDocument.objects.filter(pk=doc_id).update(
                chunk_count=doc.chunk_count,
                status=ReferenceDocument.Status.READY,
                metadata=metadata,
                updated_at=timezone.now(),
            )

        logger.info(
            "ReferenceDocument %s successfully ingested: %d pages, %d chunks",
            doc_id,
            doc.page_count,
            doc.chunk_count,
        )
        return {
            "status": "ready",
            "page_count": doc.page_count,
            "chunk_count": doc.chunk_count,
        }

    except Exception as exc:
        logger.exception("Ingestion failed for ReferenceDocument %s: %s", doc_id, exc)
        doc.status = ReferenceDocument.Status.FAILED
        doc.error_message = str(exc)
        try:
            with scoped_transaction(profile_id):
                ReferenceChunk.objects.filter(reference_document_id=doc_id).delete()
                ReferenceDocument.objects.filter(pk=doc_id).update(
                    status=ReferenceDocument.Status.FAILED,
                    error_message=str(exc),
                    updated_at=timezone.now(),
                )
        except Exception as save_exc:
            logger.exception("Failed to persist FAILED status for ReferenceDocument %s: %s", doc_id, save_exc)
        raise exc

