"""Celery task definitions (architecture §19, §24).

With CELERY_TASK_ALWAYS_EAGER (dev/test) tasks run inline; in production a
Celery worker consumes them. The `process_jobs` management command is the
broker-free DB-polling executor alternative (§24).
"""
import logging

from config.celery import app
from django.utils import timezone

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_job_task(self, job_id: str):
    from apps.jobs.services import execute_job

    execute_job(job_id)


@app.task
def reap_stuck_jobs_task():
    from apps.jobs.services import reap_stuck_jobs

    count = reap_stuck_jobs(timezone.now())
    if count:
        logger.warning("Reaped %s stuck jobs", count)
    return count


@app.task
def promote_retries_task():
    from apps.jobs.services import promote_due_retries

    count = promote_due_retries(timezone.now())
    if count:
        logger.info("Promoted %s retryable jobs to QUEUED", count)
    return count


@app.task
def reconcile_unindexed_pages_task():
    from apps.documents.models import DocumentPage
    from apps.jobs.models import Job
    from apps.retrieval.services import enqueue_page_index_job

    pages = DocumentPage.objects.filter(is_approved=True, is_ignored=False).exclude(current_revision_id=None)
    enqueued = 0
    for page in pages.iterator(chunk_size=100):
        rev = page.current_revision
        if not rev or not rev.text_hash:
            continue
        if page.indexed_text_hash == rev.text_hash:
            continue

        in_progress = Job.objects.filter(
            job_type="index_page",
            resource_id=str(page.pk),
            status__in=[Job.Status.QUEUED, Job.Status.RUNNING],
        ).exists()
        if in_progress:
            continue

        last_failed = Job.objects.filter(
            job_type="index_page",
            resource_id=str(page.pk),
            status=Job.Status.FAILED_DEAD_LETTER,
        ).exists()
        if last_failed:
            continue

        enqueue_page_index_job(page)
        enqueued += 1

    if enqueued:
        logger.info("Reconciled %d unindexed pages", enqueued)
    return enqueued


@app.task
def reap_stuck_ocr_pages_task():
    from datetime import timedelta
    from django.conf import settings
    from apps.documents.models import DocumentPage

    now = timezone.now()
    pending_timeout = timedelta(seconds=int(getattr(settings, "OCR_PENDING_TIMEOUT", 1800)))
    processing_timeout = timedelta(seconds=int(getattr(settings, "OCR_PROCESSING_TIMEOUT", 600)))

    reaped = 0
    pending_stuck = DocumentPage.objects.filter(
        ocr_status=DocumentPage.OcrStatus.PENDING,
        ocr_started_at__isnull=False,
        ocr_started_at__lt=now - pending_timeout,
    )
    for page in pending_stuck:
        page.ocr_status = DocumentPage.OcrStatus.FAILED
        page.review_status = DocumentPage.ReviewStatus.OCR_FAILED
        page.ocr_generation += 1
        page.save(update_fields=("ocr_status", "review_status", "ocr_generation"))
        reaped += 1

    processing_stuck = DocumentPage.objects.filter(
        ocr_status=DocumentPage.OcrStatus.PROCESSING,
        ocr_started_at__isnull=False,
        ocr_started_at__lt=now - processing_timeout,
    )
    for page in processing_stuck:
        page.ocr_status = DocumentPage.OcrStatus.FAILED
        page.review_status = DocumentPage.ReviewStatus.OCR_FAILED
        page.ocr_generation += 1
        page.save(update_fields=("ocr_status", "review_status", "ocr_generation"))
        reaped += 1

    if reaped:
        logger.warning("Reaped %d stuck OCR pages", reaped)
    return reaped
