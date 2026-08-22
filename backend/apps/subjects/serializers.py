from rest_framework import serializers

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class SubjectSerializer(serializers.ModelSerializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())

    class Meta:
        model = Subject
        fields = ("id", "profile", "name", "created_at")
        read_only_fields = ("id", "created_at")
