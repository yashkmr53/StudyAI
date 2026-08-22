"""Canvas domain models (architecture §4, §5).

CanvasSession is single-writer: ownership is fenced by lock_generation.
The relationship model is CanvasStroke.page_id + sequence_order — there is
deliberately no stroke_ids[] array on pages.
"""
import uuid

from django.db import models

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class CanvasSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="canvas_sessions")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="canvas_sessions")
    device_id = models.CharField(max_length=64)
    # Canonical document produced by finalizing this sheet's pages (§67).
    document = models.ForeignKey(
        "documents.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="canvas_sessions"
    )
    lock_holder = models.CharField(max_length=64, null=True, blank=True)
    lock_generation = models.PositiveIntegerField(default=1)
    lock_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("profile", "created_at")),
        ]

    def __str__(self) -> str:
        return f"session {self.pk} ({self.profile_id})"


class CanvasPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(CanvasSession, on_delete=models.CASCADE, related_name="pages")
    page_number = models.PositiveIntegerField()
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("page_number",)
        constraints = [
            models.UniqueConstraint(fields=("session", "page_number"), name="uniq_canvas_page_session_number"),
        ]

    def __str__(self) -> str:
        return f"page {self.page_number} of {self.session_id}"


class CanvasStroke(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(CanvasPage, on_delete=models.CASCADE, related_name="strokes")
    sequence_order = models.PositiveIntegerField(default=0)
    points = models.JSONField(default=list)  # flat [x0, y0, x1, y1, ...]
    client_idempotency_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sequence_order", "created_at")
        indexes = [
            models.Index(fields=("page", "sequence_order")),
        ]

    def __str__(self) -> str:
        return f"stroke {self.pk} on {self.page_id}"
