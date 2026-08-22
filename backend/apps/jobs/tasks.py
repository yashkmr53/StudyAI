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
