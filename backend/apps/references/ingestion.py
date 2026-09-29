"""Reference document ingestion service (Phase 11 §4, §22).

Orchestrates:
1. Reading PDF from object storage
2. Page text extraction (with qwen3.5:4b vision OCR fallback)
3. Deterministic chunking
4. Batched embedding generation (Qwen/Qwen3-Embedding-0.6B)
5. Idempotent ReferenceChunk + pgvector persistence
6. Updating ReferenceDocument to READY
"""
import logging
from typing import Optional

from django.conf import settings
from django.db import transaction

from apps.references.chunking import chunk_extracted_pages
from apps.references.extraction import extract_pdf_pages
from apps.references.models import ReferenceChunk, ReferenceDocument
from providers.registry import embedding_model_version, get_embedding_provider, get_object_storage

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 32


def ingest_reference_document(doc_id: str) -> dict:
    """Run full ingestion pipeline on a ReferenceDocument.

    Args:
        doc_id: UUID of ReferenceDocument.

    Returns:
        Dict with status and metrics.
    """
    try:
        doc = ReferenceDocument.objects.get(pk=doc_id)
    except ReferenceDocument.DoesNotExist:
        logger.error("ReferenceDocument %s does not exist; skipping ingestion.", doc_id)
        return {"status": "not_found"}

    if doc.status == ReferenceDocument.Status.READY and doc.chunk_count > 0:
        logger.info("ReferenceDocument %s is already READY; skipping duplicate ingestion.", doc_id)
        return {"status": "already_ready", "chunk_count": doc.chunk_count}

    doc.status = ReferenceDocument.Status.PROCESSING
    doc.error_message = ""
    doc.save(update_fields=("status", "error_message", "updated_at"))

    try:
        # 1. Fetch file bytes from storage
        storage = get_object_storage()
        if not storage.exists(doc.file_path):
            raise FileNotFoundError(f"Storage object not found: {doc.file_path}")

        pdf_bytes = storage.read_bytes(doc.file_path)

        # 2. Extract pages (with OCR fallback for scanned pages)
        pages = extract_pdf_pages(
            pdf_bytes,
            request_id=f"ref_ingest:{doc_id}",
            ocr_fallback=True,
        )
        doc.page_count = len(pages)
        doc.save(update_fields=("page_count",))

        # 3. Deterministic chunking
        chunks = chunk_extracted_pages(pages)
        if not chunks:
            raise ValueError("No text could be extracted or chunked from the PDF.")

        # 4. Batched embedding generation with canonical Qwen/Qwen3-Embedding-0.6B
        provider = get_embedding_provider()
        model_version = embedding_model_version()

        all_vectors = []
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[i : i + EMBEDDING_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            vectors = provider.embed(texts, model_version=model_version)
            all_vectors.extend(vectors)

        # 5. Persist ReferenceChunk rows in a separate transaction
        with transaction.atomic():
            # Clean up any stale chunks if re-ingesting
            ReferenceChunk.objects.filter(reference_document=doc).delete()

            chunk_rows = []
            for c, vec in zip(chunks, all_vectors):
                chunk_rows.append(
                    ReferenceChunk(
                        reference_document=doc,
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
                )
            ReferenceChunk.objects.bulk_create(chunk_rows, batch_size=100)

        # 6. Populate tsvector on PostgreSQL
        from django.db import connection

        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import SearchVector

            for r_chunk in ReferenceChunk.objects.filter(reference_document=doc).iterator(chunk_size=100):
                ReferenceChunk.objects.filter(pk=r_chunk.pk).update(
                    tsvector_content=SearchVector("text", config="english")
                )

        # 7. Mark READY
        doc.chunk_count = len(chunk_rows)
        doc.status = ReferenceDocument.Status.READY
        doc.save(update_fields=("chunk_count", "status", "updated_at"))

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
        doc.save(update_fields=("status", "error_message", "updated_at"))
        raise exc
