"""Celery task definitions for reference document ingestion (Phase 11 §4)."""
import logging

from django.conf import settings
from config.celery import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=2, default_retry_delay=15)
def ingest_reference_document_task(self, ref_doc_id: str):
    """Celery background task to process a ReferenceDocument."""
    from apps.references.ingestion import ingest_reference_document

    try:
        return ingest_reference_document(ref_doc_id)
    except Exception as exc:
        logger.error("ingest_reference_document_task failed for %s: %s", ref_doc_id, exc)
        raise self.retry(exc=exc)


def enqueue_reference_ingestion(ref_doc) -> None:
    """Trigger background ingestion for a ReferenceDocument.

    Runs inline if CELERY_TASK_ALWAYS_EAGER is True (test/eager modes),
    otherwise dispatches to Celery worker.
    """
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        from apps.references.ingestion import ingest_reference_document

        ingest_reference_document(str(ref_doc.pk))
    else:
        try:
            ingest_reference_document_task.delay(str(ref_doc.pk))
        except Exception as exc:
            logger.warning("Celery dispatch unavailable; falling back to synchronous execution: %s", exc)
            from apps.references.ingestion import ingest_reference_document

            ingest_reference_document(str(ref_doc.pk))
