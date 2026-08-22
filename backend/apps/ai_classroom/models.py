"""Generated-layer models for AI Classroom (architecture §9, §11, §12, §13).

EnrichedNote/Block/CitationBlock are GENERATED artifacts — stored
separately from source chunks and always traceable to exact source
revisions, prompt versions, model and schema versions.

Provenance (generation_method) and verification (verification_status)
are independent dimensions: a verifier verdict never rewrites how a
block was produced.
"""
import uuid

from django.db import models

from apps.documents.models import Document
from apps.jobs.models import Job
from apps.subjects.models import Subject


class EnrichedNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="enriched_notes")
    content_hash = models.CharField(max_length=64)  # sha256 of descriptor incl. prompt+model+evidence set
    revision_ids = models.JSONField(default=list)  # source revisions covered
    generation_job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    prompt_version = models.CharField(max_length=64)  # e.g. "enrichment_draft:v1"
    schema_version = models.CharField(max_length=32, default="v1")
    ai_stale = models.BooleanField(default=False)  # set when source revisions change (§27/§21)
    superseded = models.BooleanField(default=False)  # older generations retained, not active
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("document", "content_hash"),
                condition=models.Q(superseded=False),
                name="uniq_active_enriched_note_hash",
            ),
        ]
        indexes = [
            models.Index(fields=("document", "created_at")),
        ]

    def __str__(self) -> str:
        return f"enriched {self.pk} of {self.document_id}"


class EnrichedNoteBlock(models.Model):
    class GenerationMethod(models.TextChoices):
        LLM = "llm", "llm"
        RULE_BASED = "rule_based", "rule_based"
        USER_EDITED = "user_edited", "user_edited"
        TRANSCRIBED = "transcribed", "transcribed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enriched_note = models.ForeignKey(EnrichedNote, on_delete=models.CASCADE, related_name="blocks")
    block_index = models.PositiveIntegerField()
    block_type = models.CharField(max_length=32)  # overview / key_concept / gap_fill …
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    generation_method = models.CharField(max_length=20, choices=GenerationMethod.choices)
    source_chunk_ids = models.JSONField(default=list)  # chunk ids used to produce this block
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("block_index",)

    def __str__(self) -> str:
        return f"block {self.block_index} ({self.block_type}) of {self.enriched_note_id}"


class CitationBlock(models.Model):
    class VerificationStatus(models.TextChoices):
        SUPPORTED = "supported", "supported"
        PARTIALLY_SUPPORTED = "partially_supported", "partially_supported"
        UNSUPPORTED = "unsupported", "unsupported"
        NOT_VERIFIED = "not_verified", "not_verified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enriched_note_block = models.OneToOneField(
        EnrichedNoteBlock, on_delete=models.CASCADE, related_name="citation"
    )
    source_refs = models.JSONField(default=list)  # [{source_type, chunk_id, document_id, page_number, revision_id, retrieval_score}]
    verification_status = models.CharField(
        max_length=24, choices=VerificationStatus.choices, default=VerificationStatus.NOT_VERIFIED
    )
    verification_score = models.FloatField(null=True, blank=True)
    verifier_version = models.CharField(max_length=64, default="none")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("enriched_note_block__block_index",)

    def __str__(self) -> str:
        return f"citation of block {self.enriched_note_block_id} [{self.verification_status}]"


class PromptVersion(models.Model):
    """Prompt/model registry (architecture §13)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prompt_name = models.CharField(max_length=64)  # enrichment_draft / gap_detection / gap_filling
    version = models.CharField(max_length=16)
    template = models.TextField()  # system+user scaffold; evidence injected at call time
    output_schema_version = models.CharField(max_length=32)
    model = models.CharField(max_length=128)
    configuration = models.JSONField(default=dict)  # temperature etc. (mock ignores)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("prompt_name", "-version")
        constraints = [
            models.UniqueConstraint(fields=("prompt_name", "version"), name="uniq_prompt_name_version"),
        ]

    @property
    def qualified_name(self) -> str:
        return f"{self.prompt_name}:{self.version}"

    def __str__(self) -> str:
        return self.qualified_name


# ---------------------------------------------------------------- tags (§18)


class Tag(models.Model):
    """Stable academic concept: identity = (subject, stable_key); display
    names may change freely without creating a new conceptual tag."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="tags")
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    stable_key = models.CharField(max_length=64)
    display_name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("subject_id", "stable_key")
        constraints = [
            models.UniqueConstraint(fields=("subject", "stable_key"), name="uniq_tag_subject_stable_key"),
        ]

    def __str__(self) -> str:
        return f"{self.subject_id}:{self.stable_key}"


class DocumentTag(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="document_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="document_tags")
    generation_job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("tag__stable_key",)
        constraints = [
            models.UniqueConstraint(fields=("document", "tag"), name="uniq_document_tag"),
        ]


class TagChangeLog(models.Model):
    class ChangeType(models.TextChoices):
        ADDED = "added", "added"
        RENAMED = "renamed", "renamed"
        REMOVED = "removed", "removed"
        LINKED = "linked", "linked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True, related_name="change_log")
    stable_key_snapshot = models.CharField(max_length=64)
    change_type = models.CharField(max_length=16, choices=ChangeType.choices)
    old_value = models.CharField(max_length=120, blank=True)
    new_value = models.CharField(max_length=120, blank=True)
    generation_job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
