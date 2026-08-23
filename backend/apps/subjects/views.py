from django.db import IntegrityError
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.subjects.models import Subject
from apps.subjects.serializers import SubjectSerializer
from shared.authorization.services import ProfileAuthorizationService


class SubjectViewSet(viewsets.ModelViewSet):
    """Subjects scoped to profiles owned by the authenticated user (§60).

    GET /subjects                 → every subject across the user's profiles
    GET /subjects?profile={id}    → only that profile's subjects (ownership
                                    enforced; foreign/unknown ids → 404)
    """

    serializer_class = SubjectSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Subject.objects.filter(profile__user=self.request.user)
        profile_id = self.request.query_params.get("profile")
        if profile_id:
            profile = ProfileAuthorizationService.get_owned_profile(
                self.request.user, profile_id
            )
            qs = qs.filter(profile=profile)
        return qs

    def perform_create(self, serializer):
        profile = serializer.validated_data["profile"]
        ProfileAuthorizationService.ensure_profile_access(self.request.user, profile)
        try:
            serializer.save()
        except IntegrityError:
            # Race against the DB constraint; keep the message student-friendly.
            raise ValidationError(
                {"name": ["You already have a subject with this name."]}
            )
