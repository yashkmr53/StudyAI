"""Job creation, dispatch, and execution (architecture §19, §20, §24, §47).

- Job rows are the durable queue; Redis is only a broker.
- Claiming is an atomic conditional update (single winner).
- Failures: exponential backoff with jitter via next_retry_at; after
  max attempts the job dead-letters. A reaper requeues jobs stuck in
  RUNNING beyond their timeout.
- Dispatch: Celery task when a broker is available; CELERY_TASK_ALWAYS_EAGER
  runs jobs inline for dev/tests; the `process_jobs` management command is
  the DB-polling executor alternative (§24).
"""
import logging
import random
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.jobs.models import Job

logger = logging.getLogger(__name__)


def get_or_create_job(
    *,
    job_type: str,
    resource_type: str,
    resource_id: str,
    idempotency_key: str,
    profile_id=None,
    revision_id=None,
) -> tuple[Job, bool]:
    """Idempotent job creation keyed on idempotency_key (§20)."""
    existing = Job.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    try:
        job = Job.objects.create(
            job_type=job_type,
            resource_type=resource_type,
            resource_id=resource_id,
            profile_id=profile_id,
            revision_id=revision_id,
            idempotency_key=idempotency_key,
        )
        return job, True
    except IntegrityError:
        # Race: another transaction created it first.
        return Job.objects.get(idempotency_key=idempotency_key), False


def dispatch_job(job: Job) -> None:
    """Hand a QUEUED job to the broker (or run inline when eager)."""
    from apps.jobs.tasks import process_job_task

    if settings.CELERY_TASK_ALWAYS_EAGER:
        process_job_task(str(job.pk))
        return
    try:
        process_job_task.delay(str(job.pk))
    except Exception as exc:  # broker unavailable — job stays queued
        logger.warning("Broker unavailable; job %s remains queued (%s)", job.pk, exc)


def retry_backoff(job: Job) -> timedelta:
    base = getattr(settings, "JOBS_RETRY_BASE_SECONDS", 5)
    cap = getattr(settings, "JOBS_RETRY_CAP_SECONDS", 300)
    delay = min(cap, base * (2 ** max(0, job.attempt_count - 1)))
    return timedelta(seconds=delay + random.uniform(0, 2))  # exponential + jitter


def _handler_for(job: Job):
    from apps.documents.services import run_ocr_job

    handlers = {
        "ocr": run_ocr_job,
        "pdf_render": _run_pdf_render,
        "index": _run_index,
        "enrich": _run_enrich,
    }
    handler = handlers.get(job.job_type)
    if handler is None:
        raise ValueError(f"No handler registered for job_type={job.job_type}")
    return handler


def _run_pdf_render(job: Job):
    from apps.documents.note_space import NoteSpaceService

    NoteSpaceService.render_and_store(job)


def _run_index(job: Job):
    from apps.retrieval.services import run_index_job

    run_index_job(job)


def _run_enrich(job: Job):
    from apps.ai_classroom.services import run_enrichment_job

    run_enrichment_job(job)


def execute_job(job_id) -> None:
    """Claim and run one job through its full state machine (§19)."""
    job = Job.objects.get(pk=job_id)
    if not job.claim():
        return  # someone else claimed it / already terminal
    run_claimed_job(job)


def run_claimed_job(job: Job) -> None:
    """Execute a job already transitioned to RUNNING (post-claim path)."""
    handler = _handler_for(job)
    try:
        if job.profile_id:
            # §47: workers establish the trusted transaction-local RLS context.
            from shared.database.rls import profile_scoped_transaction

            with profile_scoped_transaction(job.profile_id):
                handler(job)
        else:
            handler(job)
        job.refresh_from_db()
        if job.status == Job.Status.CANCELLING:
            job.status = Job.Status.CANCELLED
            job.finished_at = timezone.now()
            job.save(update_fields=("status", "finished_at"))
        else:
            job.mark_succeeded()
    except Exception as exc:  # noqa: BLE001 — job failures are data, not crashes
        job.refresh_from_db()
        max_attempts = getattr(settings, "JOBS_MAX_ATTEMPTS", 3)
        if job.attempt_count >= max_attempts:
            job.dead_letter(str(exc))
            logger.warning("Job %s dead-lettered after %s attempts", job.pk, job.attempt_count)
        else:
            job.mark_retryable(str(exc))
            Job.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() + retry_backoff(job))
            logger.warning(
                "Job %s failed attempt %s: %s\n%s",
                job.pk, job.attempt_count, str(exc)[:300],
                traceback.format_exc()[-1500:],
            )


def promote_due_retries(now=None) -> int:
    from django.db.models import Q

    now = now or timezone.now()
    return Job.objects.filter(
        Q(status=Job.Status.FAILED_RETRYABLE)
        & (Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
    ).update(status=Job.Status.QUEUED)


def reap_stuck_jobs(now=None) -> int:
    """Requeue RUNNING jobs past their timeout (§19 reaper)."""
    now = now or timezone.now()
    timeout = timedelta(seconds=getattr(settings, "JOBS_TIMEOUT_SECONDS", 600))
    stuck = Job.objects.filter(status=Job.Status.RUNNING, started_at__lt=now - timeout)
    count = 0
    for job in stuck:
        job.mark_retryable("Reaped: exceeded job timeout")
        Job.objects.filter(pk=job.pk).update(next_retry_at=timezone.now())
        count += 1
    return count


@transaction.atomic
def cancel_job(job: Job) -> Job:
    if job.status == Job.Status.QUEUED:
        job.status = Job.Status.CANCELLED
        job.finished_at = timezone.now()
        job.save(update_fields=("status", "finished_at"))
        return job
    if job.status == Job.Status.RUNNING:
        job.status = Job.Status.CANCELLING
        job.save(update_fields=("status",))
        return job
    from shared.exceptions import ValidationError

    raise ValidationError(f"Job in status {job.status} cannot be cancelled.")
