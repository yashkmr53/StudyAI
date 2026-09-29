"""URL routing for Reference Library API (Phase 11 §12)."""
from rest_framework.routers import DefaultRouter

from apps.references.views import ReferenceDocumentViewSet

router = DefaultRouter()
router.register(r"references", ReferenceDocumentViewSet, basename="reference")

urlpatterns = router.urls
