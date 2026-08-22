import uuid

from django.db import models

from apps.profiles.models import Profile


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("profile", "name"), name="uniq_subject_profile_name"),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name
