"""Celery task definitions for reference document ingestion (Phase 11 §4)."""
import logging
from typing import Optional

from django.conf import settings
from django.db import transaction

from config.celery import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=2, default_retry_delay=15)
def ingest_reference_document_task(self, ref_doc_id: str, profile_id: Optional[str] = None):
    """Celery background task to process a ReferenceDocument under profile RLS scope."""
    from apps.references.ingestion import ingest_reference_document

    try:
        return ingest_reference_document(ref_doc_id, profile_id=profile_id)
    except Exception as exc:
        logger.error("ingest_reference_document_task failed for %s: %s", ref_doc_id, exc)
        raise self.retry(exc=exc)


def enqueue_reference_ingestion(ref_doc) -> None:
    """Trigger background ingestion for a ReferenceDocument.

    Runs inline if CELERY_TASK_ALWAYS_EAGER is True (test/eager modes),
    otherwise dispatches to Celery worker once the database transaction commits.
    """
    doc_id = str(ref_doc.pk)
    profile_id = str(ref_doc.profile_id) if ref_doc.profile_id else None

    def _dispatch():
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            from apps.references.ingestion import ingest_reference_document

            ingest_reference_document(doc_id, profile_id=profile_id)
        else:
            try:
                ingest_reference_document_task.delay(doc_id, profile_id=profile_id)
            except Exception as exc:
                logger.warning(
                    "Celery dispatch unavailable; falling back to synchronous execution: %s",
                    exc,
                )
                from apps.references.ingestion import ingest_reference_document

                ingest_reference_document(doc_id, profile_id=profile_id)

    transaction.on_commit(_dispatch)
