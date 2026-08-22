"""Administrative audit logging + provider call telemetry (§23, §25)."""
import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    actor_email = models.CharField(max_length=255, blank=True)  # survives actor deletion
    action = models.CharField(max_length=64)  # user.registered, document.created …
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("actor", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_email or 'system'} at {self.created_at:%Y-%m-%d %H:%M}"


class ProviderCallLog(models.Model):
    """One row per external-provider invocation attempt (§25 provider usage)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    # B8 token accounting
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    # D5 data-minimization metadata
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("provider", "success", "created_at")),
        ]
