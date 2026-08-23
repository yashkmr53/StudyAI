from rest_framework import serializers

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class SubjectSerializer(serializers.ModelSerializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all())

    class Meta:
        model = Subject
        fields = ("id", "profile", "name", "created_at")
        read_only_fields = ("id", "created_at")
        # The (profile, name) uniqueness is enforced with a friendly message
        # in validate() below; DRF's auto UniqueTogetherValidator would emit
        # developer-facing text ("must make a unique set").
        validators = []

    def validate(self, attrs):
        profile = attrs.get("profile") or getattr(self.instance, "profile", None)
        name = (attrs.get("name") or getattr(self.instance, "name", "") or "").strip()
        if profile and name:
            duplicate = Subject.objects.filter(profile=profile, name__iexact=name)
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError(
                    {"name": [f"You already have a subject called “{name}”."]}
                )
        return attrs
