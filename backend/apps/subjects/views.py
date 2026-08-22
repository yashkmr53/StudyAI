from rest_framework import viewsets

from apps.subjects.models import Subject
from apps.subjects.serializers import SubjectSerializer
from shared.authorization.services import ProfileAuthorizationService


class SubjectViewSet(viewsets.ModelViewSet):
    """Subjects scoped to profiles owned by the authenticated user (§60)."""

    serializer_class = SubjectSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return Subject.objects.filter(profile__user=self.request.user)

    def perform_create(self, serializer):
        profile = serializer.validated_data["profile"]
        ProfileAuthorizationService.ensure_profile_access(self.request.user, profile)
        serializer.save()
