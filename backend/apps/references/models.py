"""Reference Library models (Phase 11).

Provides first-class textbook and reference material ingestion, chunking,
provenance tracking, and pgvector embeddings for note enrichment and Ask StudyAI.
"""
import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.documents.models import Document
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.retrieval.models import AdaptiveVectorField, EMBEDDING_DIMENSIONS


class ReferenceDocument(models.Model):
    """First-class reference document (textbooks, reference PDFs, lecture materials)."""

    class SourceType(models.TextChoices):
        TEXTBOOK = "TEXTBOOK", "Textbook"
        REFERENCE_PDF = "REFERENCE_PDF", "Reference PDF"
        LECTURE_MATERIAL = "LECTURE_MATERIAL", "Lecture Material"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
        default=SourceType.TEXTBOOK,
    )
    # File path / object storage key in MinIO or local storage
    file_path = models.CharField(max_length=512, blank=True, default="")
    # Optional subject scope
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reference_documents",
    )
    # Optional profile scope (null = global platform reference; non-null = profile private)
    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reference_documents",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    page_count = models.PositiveIntegerField(null=True, blank=True, default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "subject")),
            models.Index(fields=("profile", "status")),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.source_type}, {self.status})"


class ReferenceChunk(models.Model):
    """Chunk of text from a ReferenceDocument with pgvector embedding and provenance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_document = models.ForeignKey(
        ReferenceDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField(default=0)
    text = models.TextField()
    content_hash = models.CharField(max_length=64, blank=True, default="")
    embedding = AdaptiveVectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedding_model = models.CharField(max_length=128, null=True, blank=True)
    embedding_version = models.CharField(max_length=64, null=True, blank=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    chapter = models.CharField(max_length=255, blank=True, default="")
    section = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    tsvector_content = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("reference_document_id", "chunk_index")
        indexes = [
            models.Index(fields=("reference_document", "chunk_index")),
            GinIndex(fields=("tsvector_content",), name="idx_refchunk_gin_tsv"),
        ]

    def __str__(self) -> str:
        doc_title = self.reference_document.title if self.reference_document_id else "unknown"
        return f"chunk {self.chunk_index} of {doc_title} (p.{self.page_number})"


# --- Legacy Curated Book Models (Preserved for compatibility) ---

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
