"""Durable job records (architecture §19).

Every asynchronous operation is represented by a Job row. PostgreSQL is
the durable source of truth; Redis is only a broker. Jobs are claimed with
a DB-level conditional update to prevent double-processing, and every job
carries a unique idempotency key.
"""
import uuid

from django.db import models
from django.utils import timezone


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "QUEUED"
        RUNNING = "running", "RUNNING"
        FAILED_RETRYABLE = "failed_retryable", "FAILED_RETRYABLE"
        FAILED_DEAD_LETTER = "failed_dead_letter", "FAILED_DEAD_LETTER"
        CANCELLING = "cancelling", "CANCELLING"
        CANCELLED = "cancelled", "CANCELLED"
        SUCCEEDED = "succeeded", "SUCCEEDED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=64)
    profile_id = models.UUIDField(null=True, blank=True)
    revision_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED)
    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # For enrichment coalescing (B7): link to previous job if this job coalesced
    coalesced_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="coalesced_jobs")

    class Meta:
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("job_type", "resource_type", "resource_id")),
        ]

    def claim(self) -> bool:
        """Atomically transition QUEUED → RUNNING; returns False if already claimed."""
        updated = type(self).objects.filter(
            pk=self.pk,
            status=self.Status.QUEUED,
        ).update(status=self.Status.RUNNING, started_at=timezone.now(), attempt_count=models.F("attempt_count") + 1)
        return bool(updated)

    def mark_succeeded(self) -> None:
        self.status = self.Status.SUCCEEDED
        self.finished_at = timezone.now()
        self.save(update_fields=("status", "finished_at"))

    def mark_retryable(self, error: str) -> None:
        self.status = self.Status.FAILED_RETRYABLE
        self.last_error = error[:4000]
        self.save(update_fields=("status", "last_error"))

    def dead_letter(self, error: str) -> None:
        self.status = self.Status.FAILED_DEAD_LETTER
        self.last_error = error[:4000]
        self.finished_at = timezone.now()
        self.save(update_fields=("status", "last_error", "finished_at"))
