from rest_framework import serializers

from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from apps.profiles.models import Profile
from apps.subjects.models import Subject


class DocumentCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    source_type = serializers.ChoiceField(choices=[Document.SourceType.IMAGE, Document.SourceType.PDF])
    filename = serializers.CharField(max_length=255)


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "profile", "subject", "source", "source_type", "schema_version", "created_at")


class DocumentPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentPage
        fields = (
            "id", "document", "page_number", "image_ref",
            "current_revision_id", "needs_review", "ocr_status", "created_at",
        )


class DocumentLineSerializer(serializers.Serializer):
    line_index = serializers.IntegerField(min_value=0)
    text = serializers.CharField(max_length=10000)
    bbox = serializers.ListField(child=serializers.FloatField(), required=False, allow_null=True)


class RevisionCreateSerializer(serializers.Serializer):
    """Two modes (§46/§48): finalize an uploaded object, or submit edited lines."""

    page_id = serializers.UUIDField()
    lines = DocumentLineSerializer(many=True, required=False)

    def validate(self, attrs):
        if attrs.get("lines") is None:
            # finalize-upload mode: no body fields allowed beyond page_id
            pass
        return attrs


class DocumentPageRevisionSerializer(serializers.ModelSerializer):
    line_count = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()

    class Meta:
        model = DocumentPageRevision
        fields = (
            "id", "page", "revision_number", "content_hash", "content_snapshot",
            "edited_by", "ocr_status", "ocr_provider", "line_count", "lines",
            "created_at",
        )

    def get_line_count(self, obj) -> int:
        return obj.lines.count()

    def get_lines(self, obj) -> list:
        return [
            {
                "line_index": l.line_index,
                "text": l.text,
                "bbox": l.bbox,
                "confidence_score": l.confidence_score,
                "is_heading": bool(l.is_heading),
            }
            for l in obj.lines.order_by("line_index")
        ]


class RetryProcessingSerializer(serializers.Serializer):
    page_id = serializers.UUIDField()
