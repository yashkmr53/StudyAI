from rest_framework import serializers

from apps.profiles.models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ("id", "name", "module", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
