"""Tags API (architecture §18, §60).

GET    /api/v1/tags                    list tags
GET    /api/v1/tags/{id}               retrieve tag
POST   /api/v1/tags/{id}/rename        rename tag
"""
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ai_classroom.models import Tag, TagChangeLog
from apps.ai_classroom.serializers import TagSerializer
from apps.ai_classroom.tagging import TaggingService
from shared.exceptions import ResourceNotFound, ValidationError


class TagViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TagSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        # Scope to subjects the user has access to via their profiles
        from apps.profiles.models import Profile
        from apps.subjects.models import Subject

        profile_ids = Profile.objects.filter(user=self.request.user).values_list("id", flat=True)
        subject_ids = Subject.objects.filter(profile_id__in=profile_ids).values_list("id", flat=True)
        return Tag.objects.filter(subject_id__in=subject_ids).select_related("subject")

    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        """Rename a tag's display name.
        
        POST /api/v1/tags/{id}/rename/
        Body: {"name": "new display name"}
        
        Returns the updated tag with new display name.
        """
        tag = self.get_object()
        new_name = request.data.get("name")
        
        if not new_name or not new_name.strip():
            raise ValidationError("Tag name cannot be empty.")
        
        if len(new_name) > 120:
            raise ValidationError("Tag name cannot exceed 120 characters.")
        
        if tag.display_name == new_name.strip():
            return Response(TagSerializer(tag).data)
        
        TaggingService.rename_tag(tag, new_name.strip())
        tag.refresh_from_db()
        
        return Response(TagSerializer(tag).data)