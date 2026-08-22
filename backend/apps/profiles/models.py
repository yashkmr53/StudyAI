import uuid

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Primary tenant boundary: every user-owned resource scopes to a profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profiles")
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "name"), name="uniq_profile_user_name"),
        ]
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.user.email}/{self.name}"
