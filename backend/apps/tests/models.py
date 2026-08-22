"""Adaptive tests + mastery scoring models (architecture §17, §18, §55–56)."""
import uuid

from django.db import models

from apps.profiles.models import Profile
from apps.questions.models import Question
from apps.subjects.models import Subject


class TestInstance(models.Model):
    class Type(models.TextChoices):
        PRACTICE = "practice", "practice"
        MOCK = "mock", "mock"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="tests")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="tests")
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.PRACTICE)
    scheduled_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class TestQuestion(models.Model):
    test = models.ForeignKey(TestInstance, on_delete=models.CASCADE, related_name="test_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="test_questions")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order",)
        constraints = [
            models.UniqueConstraint(fields=("test", "question"), name="uniq_test_question"),
        ]


class TestAttempt(models.Model):
    test = models.ForeignKey(TestInstance, on_delete=models.CASCADE, related_name="attempts")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="attempts")
    selected_index = models.PositiveIntegerField()
    correct = models.BooleanField()
    confidence = models.FloatField(null=True, blank=True)  # user-reported 0..1
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("answered_at",)
        constraints = [
            models.UniqueConstraint(fields=("test", "question"), name="uniq_attempt_per_test_question"),
        ]


class MasteryScore(models.Model):
    """Per (profile, tag) mastery. Unattempted tags simply have no row —
    the service treats them as not_assessed, never zero (§18)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="mastery_scores")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="mastery_scores")
    tag = models.ForeignKey("ai_classroom.Tag", on_delete=models.CASCADE, related_name="mastery_scores")
    mastery = models.FloatField(default=0.0)  # 0..1 EMA
    attempt_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    last_assessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("tag__stable_key",)
        constraints = [
            models.UniqueConstraint(fields=("profile", "tag"), name="uniq_mastery_profile_tag"),
        ]
