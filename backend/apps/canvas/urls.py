from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.canvas.views import CanvasPageViewSet, CanvasSessionViewSet

router = DefaultRouter(trailing_slash=False)
router.register("canvas/sessions", CanvasSessionViewSet, basename="canvas-sessions")
router.register("canvas/pages", CanvasPageViewSet, basename="canvas-pages")

urlpatterns = [
    path("", include(router.urls)),
]
