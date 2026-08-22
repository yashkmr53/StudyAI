"""Canonical document models (architecture §6).

The canonical layer is the boundary between ingestion and the product
modules. Revisions are immutable: edits create new revisions, never
mutations. DocumentLine belongs to a specific page revision so historical
processing stays reproducible.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class Document(models.Model):
    class Source(models.TextChoices):
        UPLOAD = "upload", "upload"
        CANVAS = "canvas", "canvas"
        REFERENCE = "reference", "reference"

    class SourceType(models.TextChoices):
        IMAGE = "image", "image"
        PDF = "pdf", "pdf"
        CANVAS_PAGE = "canvas_page", "canvas_page"
        REFERENCE = "reference", "reference"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Nullable only for platform reference books (source="reference").
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True, related_name="documents")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    source = models.CharField(max_length=20, choices=Source.choices)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    schema_version = models.CharField(max_length=16, default="1")
    # Plain UUID until the references app gains its model (Phase 5); no FK yet.
    reference_book_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("profile", "created_at")),
        ]

    def __str__(self) -> str:
        return f"document {self.pk} ({self.source}/{self.source_type})"


class DocumentPage(models.Model):
    class OcrStatus(models.TextChoices):
        PENDING = "pending", "pending"
        PROCESSING = "processing", "processing"
        COMPLETED = "completed", "completed"
        NEEDS_REVIEW = "needs_review", "needs_review"
        FAILED = "failed", "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="pages")
    page_number = models.PositiveIntegerField()
    image_ref = models.CharField(max_length=512, null=True, blank=True)  # object storage key
    # Plain UUID to avoid a circular FK (revision → page → revision); the
    # service layer keeps it consistent with the latest revision.
    current_revision_id = models.UUIDField(null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    ocr_status = models.CharField(max_length=20, choices=OcrStatus.choices, default=OcrStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("page_number",)
        constraints = [
            models.UniqueConstraint(fields=("document", "page_number"), name="uniq_document_page_number"),
        ]

    def __str__(self) -> str:
        return f"page {self.page_number} of {self.document_id}"


class DocumentPageRevision(models.Model):
    class OcrStatus(models.TextChoices):
        PENDING = "pending", "pending"
        PROCESSING = "processing", "processing"
        COMPLETED = "completed", "completed"
        NEEDS_REVIEW = "needs_review", "needs_review"
        FAILED = "failed", "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(DocumentPage, on_delete=models.CASCADE, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)  # sha256 hex of canonical content
    content_snapshot = models.JSONField(default=dict)  # canonical lines snapshot for reproducibility
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    ocr_status = models.CharField(max_length=20, choices=OcrStatus.choices, default=OcrStatus.PENDING)
    ocr_provider = models.CharField(max_length=64, null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("revision_number",)
        constraints = [
            models.UniqueConstraint(fields=("page", "revision_number"), name="uniq_page_revision_number"),
        ]

    def __str__(self) -> str:
        return f"rev {self.revision_number} of {self.page_id}"


class DocumentLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page_revision = models.ForeignKey(DocumentPageRevision, on_delete=models.CASCADE, related_name="lines")
    line_index = models.PositiveIntegerField()
    text = models.TextField()
    bbox = models.JSONField(null=True, blank=True)  # [x, y, w, h]
    confidence_score = models.FloatField(null=True, blank=True)
    # Headings are rendered as such ONLY when explicitly flagged by the
    # source (provider metadata or user edit) — never inferred (§7/§49).
    is_heading = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("line_index",)
        constraints = [
            models.UniqueConstraint(fields=("page_revision", "line_index"), name="uniq_revision_line_index"),
        ]

    def __str__(self) -> str:
        return f"line {self.line_index} of rev {self.page_revision_id}"


class DigitizedDocument(models.Model):
    """Immutable typed-PDF artifact tied to exact page revisions (architecture §7).

    Regeneration with unchanged revisions + renderer version returns the
    same artifact; any revision change produces a NEW artifact. Old
    artifacts are retained.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="digitized_documents")
    content_hash = models.CharField(max_length=64)  # sha256 of descriptor incl. renderer_version
    revision_ids = models.JSONField(default=list)  # [{revision_id, page_number}] used for this PDF
    pdf_ref = models.CharField(max_length=512)  # object storage key
    renderer_version = models.CharField(max_length=64)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("document", "content_hash"), name="uniq_digitized_document_hash"),
        ]

    def __str__(self) -> str:
        return f"digitized {self.pk} of {self.document_id}"
