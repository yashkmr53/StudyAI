from rest_framework import serializers

from apps.documents.models import Document, DocumentPage, DocumentPageRevision
from apps.notebooks.models import Notebook
from apps.profiles.models import Profile
from apps.subjects.models import Subject


class DocumentCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    notebook = serializers.PrimaryKeyRelatedField(queryset=Notebook.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default="Untitled Note")
    source_type = serializers.ChoiceField(choices=[Document.SourceType.IMAGE, Document.SourceType.PDF])
    filename = serializers.CharField(max_length=255)

    def validate(self, attrs):
        profile = attrs.get("profile")
        subject = attrs.get("subject")
        notebook = attrs.get("notebook")

        if subject and subject.profile_id != profile.id:
            raise serializers.ValidationError({"subject": "Subject does not belong to the requested profile."})

        if notebook:
            if notebook.profile_id != profile.id:
                raise serializers.ValidationError({"notebook": "Notebook does not belong to the requested profile."})
            if notebook.subject is not None:
                if subject is not None and notebook.subject_id != subject.id:
                    raise serializers.ValidationError({"notebook": "Notebook subject does not match document subject."})
                elif subject is None:
                    attrs["subject"] = notebook.subject
                    subject = notebook.subject

        # Check duplicate note title in (profile, subject, notebook) if title is provided
        title_val = (attrs.get("title") or attrs.get("filename") or "").strip()
        if title_val and title_val.lower() != "untitled note":
            duplicate = Document.objects.filter(
                profile=profile,
                subject=attrs.get("subject"),
                notebook=notebook,
                title__iexact=title_val,
            )
            if duplicate.exists():
                scope_desc = "this folder" if notebook else "this subject"
                raise serializers.ValidationError(
                    {"title": [f"A note with this name already exists in {scope_desc}."]}
                )

        return attrs


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "profile", "subject", "notebook", "title", "source", "source_type", "schema_version", "created_at")
        read_only_fields = ("id", "profile", "source", "source_type", "schema_version", "created_at")


class DocumentUpdateSerializer(serializers.ModelSerializer):
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    notebook = serializers.PrimaryKeyRelatedField(queryset=Notebook.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)

    class Meta:
        model = Document
        fields = ("title", "subject", "notebook")

    def validate(self, attrs):
        document = self.instance
        profile = document.profile

        target_subject = attrs.get("subject", document.subject) if "subject" in attrs else document.subject
        target_notebook = attrs.get("notebook", document.notebook) if "notebook" in attrs else document.notebook

        # Validate subject profile
        if target_subject is not None:
            if target_subject.profile_id != profile.id:
                raise serializers.ValidationError({"subject": "Subject does not belong to the document's profile."})

        # Validate notebook profile and subject consistency
        if target_notebook is not None:
            if target_notebook.profile_id != profile.id:
                raise serializers.ValidationError({"notebook": "Notebook does not belong to the document's profile."})
            if target_notebook.subject is not None:
                if target_subject is not None and target_notebook.subject_id != target_subject.id:
                    raise serializers.ValidationError({"notebook": "Notebook subject does not match document subject."})
                elif target_subject is None:
                    attrs["subject"] = target_notebook.subject
                    target_subject = target_notebook.subject

        # Validate title not empty if provided
        if "title" in attrs:
            cleaned_title = attrs["title"].strip()
            if not cleaned_title:
                attrs["title"] = "Untitled Note"
            else:
                attrs["title"] = cleaned_title

        # Check duplicate note title in the target folder / subject
        effective_title = attrs.get("title", document.title).strip()
        if effective_title and effective_title.lower() != "untitled note":
            duplicate = Document.objects.filter(
                profile=profile,
                subject=target_subject,
                notebook=target_notebook,
                title__iexact=effective_title,
            ).exclude(pk=document.pk)
            if duplicate.exists():
                scope_desc = "this folder" if target_notebook else "this subject"
                raise serializers.ValidationError(
                    {"title": [f"A note with this name already exists in {scope_desc}."]}
                )

        return attrs


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
