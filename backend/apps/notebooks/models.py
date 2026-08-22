"""Notebooks module models (architecture §60 CRUD).

Mirrors the canonical Document/DocumentPage/DocumentLine layer but simplified
for handwritten note-taking without OCR pipeline. Each notebook belongs to a
profile and subject; pages contain stroke data (client-side canvas).
"""
import uuid

from django.conf import settings
from django.db import models

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class Notebook(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="notebooks")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="notebooks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover_image_ref = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("profile", "created_at")),
        ]

    def __str__(self) -> str:
        return f"Notebook {self.pk}: {self.title}"


class NotebookPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="pages")
    page_number = models.PositiveIntegerField()
    # Canvas state stored as JSON: strokes, background, viewport
    canvas_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("page_number",)
        constraints = [
            models.UniqueConstraint(fields=("notebook", "page_number"), name="uniq_notebook_page_number"),
        ]

    def __str__(self) -> str:
        return f"Page {self.page_number} of Notebook {self.notebook_id}"


class NotebookLine(models.Model):
    """Individual stroke/line on a page — mirrors DocumentLine but for vector ink."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(NotebookPage, on_delete=models.CASCADE, related_name="lines")
    line_index = models.PositiveIntegerField()
    # Stroke data: points array [x1, y1, x2, y2, ...] in canvas coordinates
    points = models.JSONField(default=list)
    # Optional: color, width, tool type for rendering
    color = models.CharField(max_length=20, default="#000000")
    width = models.FloatField(default=2.0)
    tool = models.CharField(max_length=20, default="pen")  # pen, highlighter, eraser
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("line_index",)
        constraints = [
            models.UniqueConstraint(fields=("page", "line_index"), name="uniq_notebook_page_line_index"),
        ]

    def __str__(self) -> str:
        return f"Line {self.line_index} of Page {self.page_id}"