from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from providers.storage.views import StorageDownloadView, StorageUploadView
from shared.observability.views import HealthzView, ReadyzView, StatusView

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.profiles.urls")),
    path("", include("apps.canvas.urls")),
    path("", include("apps.documents.urls")),  # incl. search + audit routes
    path("status", StatusView.as_view(), name="status"),
    path("storage/upload/<path:key>", StorageUploadView.as_view()),
    path("storage/download/<path:key>", StorageDownloadView.as_view()),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include(api_v1)),
    path("healthz", HealthzView.as_view()),
    path("readyz", ReadyzView.as_view()),
]
