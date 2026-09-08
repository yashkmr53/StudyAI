import uuid

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Primary tenant boundary: every user-owned resource scopes to a profile."""

    class Module(models.TextChoices):
        NOTE_SPACE = "NOTE_SPACE", "NoteSpace"
        AI_CLASSROOM = "AI_CLASSROOM", "AI Classroom"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profiles")
    name = models.CharField(max_length=120)
    module = models.CharField(max_length=20, choices=Module.choices, default=Module.NOTE_SPACE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "module", "name"), name="uniq_profile_user_module_name"),
        ]
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.user.email}/{self.module}/{self.name}"
