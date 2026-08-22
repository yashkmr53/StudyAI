from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.profiles.views import ProfileViewSet
from apps.subjects.views import SubjectViewSet

router = DefaultRouter(trailing_slash=False)
router.register("profiles", ProfileViewSet, basename="profiles")
router.register("subjects", SubjectViewSet, basename="subjects")

urlpatterns = [
    path("", include(router.urls)),
]
