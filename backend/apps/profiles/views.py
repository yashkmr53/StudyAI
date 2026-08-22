from rest_framework import viewsets

from apps.profiles.models import Profile
from apps.profiles.serializers import ProfileSerializer


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Profile.objects.filter(user=self.request.user)
