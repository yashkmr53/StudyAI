"""Staff-only audit listing (§23 administrative audit logging)."""
from rest_framework import serializers
from rest_framework.generics import ListAPIView

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField()

    class Meta:
        model = AuditLog
        fields = ("id", "actor_email", "action", "resource_type", "resource_id",
                  "metadata", "ip_address", "created_at")


class AuditLogListView(ListAPIView):
    permission_classes = [__import__('rest_framework.permissions', fromlist=['IsAdminUser']).IsAdminUser]
    """GET /api/v1/audit — staff only. Filter: ?action=…"""

    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        action = self.request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        return qs
