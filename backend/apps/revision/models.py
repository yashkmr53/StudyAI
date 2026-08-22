"""Revision goals + computed plans (architecture §58)."""
import uuid

from django.db import models

from apps.profiles.models import Profile
from apps.subjects.models import Subject


class RevisionGoal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="revision_goals")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="revision_goals")
    target_date = models.DateField()
    hours_per_week = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("target_date",)
