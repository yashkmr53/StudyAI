from rest_framework import serializers

from apps.profiles.models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ("id", "name", "module", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Profile name cannot be blank.")
        return cleaned

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) or getattr(self.instance, "user", None)
        module = (
            attrs.get("module")
            or (request.headers.get("X-Active-Module") if request else None)
            or getattr(self.instance, "module", None)
            or Profile.Module.NOTE_SPACE
        )
        name = attrs.get("name") or getattr(self.instance, "name", "")
        if user and module and name:
            qs = Profile.objects.filter(user=user, module=module, name__iexact=name.strip())
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": ["You already have a profile with this name in this module."]}
                )
        return attrs
