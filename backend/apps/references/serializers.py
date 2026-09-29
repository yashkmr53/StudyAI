"""Serializers for Reference Library API (Phase 11 §12)."""
from rest_framework import serializers

from apps.references.models import ReferenceChunk, ReferenceDocument
from apps.subjects.models import Subject


class ReferenceDocumentSerializer(serializers.ModelSerializer):
    subject_name = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()

    class Meta:
        model = ReferenceDocument
        fields = [
            "id",
            "title",
            "source_type",
            "subject",
            "subject_name",
            "profile",
            "scope",
            "status",
            "page_count",
            "chunk_count",
            "error_message",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "profile",
            "scope",
            "status",
            "page_count",
            "chunk_count",
            "error_message",
            "created_at",
            "updated_at",
        ]

    def get_subject_name(self, obj) -> str | None:
        return obj.subject.name if obj.subject else None

    def get_scope(self, obj) -> str:
        return "global" if obj.profile_id is None else "profile"


class ReferenceChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferenceChunk
        fields = [
            "id",
            "chunk_index",
            "text",
            "page_number",
            "chapter",
            "section",
            "created_at",
        ]


class ReferenceUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(max_length=255, required=False)
    source_type = serializers.ChoiceField(
        choices=ReferenceDocument.SourceType.choices,
        default=ReferenceDocument.SourceType.TEXTBOOK,
    )
    subject_id = serializers.UUIDField(required=False, allow_null=True)
    subject = serializers.UUIDField(required=False, allow_null=True)
    is_global = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        if not attrs.get("subject_id") and attrs.get("subject"):
            attrs["subject_id"] = attrs["subject"]
        return attrs

    def validate_file(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF documents are supported for reference library.")
        return value
