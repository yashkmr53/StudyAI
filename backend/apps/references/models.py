"""Platform-curated reference books (architecture §15).

Content flows through the canonical ingestion layer: each book owns a
Document (source="reference") whose pages/chunks are indexed like user
notes. Only books in READY status participate in retrieval. Users cannot
create or modify reference books — there is deliberately no public write
API; ingestion happens via the admin management command.
"""
import uuid

from django.db import models

from apps.documents.models import Document
from apps.subjects.models import Subject


class ReferenceBook(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "draft"
        PROCESSING = "processing", "processing"
        READY = "ready", "ready"
        FAILED = "failed", "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="reference_books")
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    edition = models.CharField(max_length=64, blank=True)
    isbn = models.CharField(max_length=32, blank=True)
    document = models.OneToOneField(Document, on_delete=models.SET_NULL, null=True, blank=True, related_name="reference_book")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("title",)

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class ReferenceBookChapter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(ReferenceBook, on_delete=models.CASCADE, related_name="chapters")
    chapter_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    page_range_start = models.PositiveIntegerField()
    page_range_end = models.PositiveIntegerField()

    class Meta:
        ordering = ("chapter_number",)
        constraints = [
            models.UniqueConstraint(fields=("book", "chapter_number"), name="uniq_reference_chapter_number"),
        ]

    def __str__(self) -> str:
        return f"ch{self.chapter_number} of {self.book_id}"
