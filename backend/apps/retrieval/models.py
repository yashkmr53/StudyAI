"""Source-layer chunks + hybrid index (architecture §9, §10, §14).

NoteChunk IS source material for retrieval — never a container for
generated prose. Embeddings are stored inline (spec §10 shape) with the
model/version recorded per chunk; tsvector_content powers keyword search;
stale chunks are excluded from retrieval but retained for auditability.
"""
import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.documents.models import Document
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from pgvector.django import VectorField

EMBEDDING_DIMENSIONS = int(getattr(settings, "EMBEDDING_DIMENSIONS", 384))


class AdaptiveVectorField(VectorField):
    """vector(N) on PostgreSQL; plain text elsewhere (SQLite unit tests).

    pgvector normally relies on a psycopg adapter to serialize Vector
    objects; other backends have none, so we emit the bracket format
    ourselves.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return super().db_type(connection)
        return "text"

    def get_prep_value(self, value):
        if connection_vendor_is_postgres():
            return super().get_prep_value(value)
        if value is None:
            return None
        values = value.to_list() if hasattr(value, "to_list") else list(value)
        return "[" + ",".join(repr(float(v)) for v in values) + "]"


def connection_vendor_is_postgres() -> bool:
    from django.db import connection

    return connection.vendor == "postgresql"


class NoteChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    # Nullable: reference-book chunks are platform-wide (no owning profile).
    profile = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks")
    # Primary revision (first in range) — kept for the §66 constraint; the
    # full set lives in revision_ids (deviation E-002).
    revision_id = models.UUIDField()
    revision_ids = models.JSONField(default=list)
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    chunk_index = models.PositiveIntegerField(default=0)
    content = models.TextField()
    content_hash = models.CharField(max_length=64)
    source_type = models.CharField(max_length=20)
    reference_book = models.ForeignKey(
        "references.ReferenceBook", on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks"
    )
    embedding = AdaptiveVectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedding_model = models.CharField(max_length=128, null=True, blank=True)
    embedding_version = models.CharField(max_length=64, null=True, blank=True)
    tsvector_content = SearchVectorField(null=True, blank=True)
    stale = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("document_id", "chunk_index")
        constraints = [
            models.UniqueConstraint(
                fields=("revision_id", "content_hash", "chunk_index"),
                name="uniq_notechunk_revision_hash_index",
            ),
        ]
        indexes = [
            models.Index(fields=("document", "stale")),
            GinIndex(fields=("tsvector_content",), name="idx_notechunk_gin_tsv"),
        ]

    def __str__(self) -> str:
        return f"chunk {self.chunk_index} of {self.document_id} [p{self.page_start}-{self.page_end}]"
