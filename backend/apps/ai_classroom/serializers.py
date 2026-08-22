"""Tags serializers (architecture §18)."""
from rest_framework import serializers

from apps.ai_classroom.models import Tag, TagChangeLog


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            "id",
            "subject",
            "parent",
            "stable_key",
            "display_name",
            "created_at",
        )


class TagChangeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagChangeLog
        fields = (
            "id",
            "tag",
            "stable_key_snapshot",
            "change_type",
            "old_value",
            "new_value",
            "created_at",
        )