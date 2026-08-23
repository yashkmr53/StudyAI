from django.db import IntegrityError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.profiles.models import Profile
from apps.profiles.serializers import ProfileSerializer


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Profile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Tenant owner is always the authenticated user, never client input.
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError(
                {"name": ["You already have a profile with this name."]}
            )

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise ValidationError(
                {"name": ["You already have a profile with this name."]}
            )
