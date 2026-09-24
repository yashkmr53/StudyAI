from rest_framework import serializers

from apps.notebooks.models import Notebook, NotebookPage, NotebookLine
from apps.profiles.models import Profile
from apps.subjects.models import Subject


class NotebookCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Folder name cannot be blank.")
        return cleaned

    def validate(self, attrs):
        profile = attrs.get("profile")
        subject = attrs.get("subject")
        title = attrs.get("title", "").strip()
        attrs["title"] = title
        if profile and title:
            qs = Notebook.objects.filter(profile=profile, subject=subject, title__iexact=title)
            if qs.exists():
                raise serializers.ValidationError(
                    {"title": ["A folder with this name already exists in this subject."]}
                )
        return attrs


class NotebookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notebook
        fields = ("id", "profile", "subject", "title", "description", "cover_image_ref", "created_at", "updated_at")

    def validate_title(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Folder name cannot be blank.")
        return cleaned

    def validate(self, attrs):
        profile = attrs.get("profile") or getattr(self.instance, "profile", None)
        subject = attrs.get("subject") if "subject" in attrs else getattr(self.instance, "subject", None)
        title = attrs.get("title")
        if title is not None:
            title = title.strip()
            attrs["title"] = title
            if not title:
                raise serializers.ValidationError({"title": ["Folder name cannot be blank."]})
        else:
            title = (getattr(self.instance, "title", "") or "").strip()

        if profile and title:
            qs = Notebook.objects.filter(profile=profile, subject=subject, title__iexact=title)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"title": ["A folder with this name already exists in this subject."]}
                )
        return attrs


class NotebookPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotebookPage
        fields = ("id", "notebook", "page_number", "canvas_state", "created_at", "updated_at")


class NotebookLineSerializer(serializers.Serializer):
    line_index = serializers.IntegerField(min_value=0)
    points = serializers.ListField(child=serializers.FloatField())
    color = serializers.CharField(max_length=20, required=False, default="#000000")
    width = serializers.FloatField(required=False, default=2.0)
    tool = serializers.CharField(max_length=20, required=False, default="pen")


class NotebookPageCreateSerializer(serializers.Serializer):
    notebook = serializers.PrimaryKeyRelatedField(queryset=Notebook.objects.all())
    page_number = serializers.IntegerField(min_value=1)
    canvas_state = serializers.JSONField(required=False, default=dict)


class NotebookPageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotebookPage
        fields = ("canvas_state", "page_number")
        extra_kwargs = {
            "page_number": {"min_value": 1, "required": False},
            "canvas_state": {"required": False},
        }