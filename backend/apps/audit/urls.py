from django.urls import path

from apps.audit.views import AuditLogListView

urlpatterns = [
    path("audit", AuditLogListView.as_view(), name="audit-list"),
]
