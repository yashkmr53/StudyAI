from rest_framework import serializers

from apps.canvas.models import CanvasPage, CanvasSession, CanvasStroke
from apps.profiles.models import Profile
from apps.subjects.models import Subject


class CanvasSessionCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())
    device_id = serializers.CharField(max_length=64)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)


class CanvasSessionSerializer(serializers.ModelSerializer):
    pages = serializers.SerializerMethodField()

    class Meta:
        model = CanvasSession
        fields = (
            "id", "profile", "subject", "device_id",
            "lock_holder", "lock_generation", "lock_expires_at",
            "pages", "created_at", "updated_at",
        )

    def get_pages(self, obj) -> list:
        return [
            {
                "id": str(p.id),
                "page_number": p.page_number,
                "is_finalized": p.is_finalized,
            }
            for p in obj.pages.all()
        ]


class CanvasPageSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=CanvasSession.objects.all())

    class Meta:
        model = CanvasPage
        fields = ("id", "session", "page_number", "is_finalized", "finalized_at", "created_at")
        read_only_fields = ("id", "is_finalized", "finalized_at", "created_at")


class StrokeInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    sequence_order = serializers.IntegerField(min_value=0, default=0)
    points = serializers.ListField(child=serializers.FloatField(), min_length=2)
    client_idempotency_key = serializers.CharField(max_length=64)


class StrokeBatchSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    lock_generation = serializers.IntegerField(min_value=1)
    strokes = StrokeInputSerializer(many=True)


class FinalizeSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    lock_generation = serializers.IntegerField(min_value=1)


class HeartbeatSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    lock_generation = serializers.IntegerField(min_value=1)


class TakeoverSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
