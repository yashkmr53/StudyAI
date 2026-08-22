from rest_framework import serializers

from apps.notebooks.models import Notebook, NotebookPage, NotebookLine
from apps.profiles.models import Profile
from apps.subjects.models import Subject


class NotebookCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)


class NotebookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notebook
        fields = ("id", "profile", "subject", "title", "description", "cover_image_ref", "created_at", "updated_at")


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