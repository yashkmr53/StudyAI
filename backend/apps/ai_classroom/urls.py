from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.ai_classroom.views import TagViewSet

router = DefaultRouter(trailing_slash=False)
router.register("tags", TagViewSet, basename="tags")

urlpatterns = [
    path("", include(router.urls)),
]