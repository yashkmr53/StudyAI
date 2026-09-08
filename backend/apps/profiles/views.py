from django.db import IntegrityError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.profiles.models import Profile
from apps.profiles.serializers import ProfileSerializer


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Profile.objects.filter(user=self.request.user)
        module = self.request.headers.get("X-Active-Module")
        if module in dict(Profile.Module.choices):
            qs = qs.filter(module=module)
        return qs

    def get_object(self):
        obj = super().get_object()
        module = self.request.headers.get("X-Active-Module")
        if module and obj.module != module:
            raise PermissionDenied("Profile does not belong to the requested module.")
        return obj

    def perform_create(self, serializer):
        module = self.request.headers.get("X-Active-Module")
        if module not in dict(Profile.Module.choices):
            module = Profile.Module.NOTE_SPACE
        try:
            serializer.save(user=self.request.user, module=module)
        except IntegrityError:
            raise ValidationError(
                {"name": ["You already have a profile with this name in this module."]}
            )

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise ValidationError(
                {"name": ["You already have a profile with this name."]}
            )
