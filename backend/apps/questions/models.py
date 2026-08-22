"""Revision-aware questions (architecture §17, §54).

Questions bind to their exact source revision and chunk; when the source
becomes stale the question is flagged (never deleted) so historical
attempts remain intact.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.documents.models import Document


class Question(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "easy"
        MEDIUM = "medium", "medium"
        HARD = "hard", "hard"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="questions")
    source_revision_id = models.UUIDField()
    source_chunk_id = models.UUIDField()
    difficulty = models.CharField(max_length=8, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    prompt = models.TextField()
    options = models.JSONField(default=list)  # list[str]
    answer_index = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    question_key = models.CharField(max_length=64)  # stable identity within revision+hash
    generation_model = models.CharField(max_length=128)
    prompt_version = models.CharField(max_length=64)
    stale = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source_revision_id", "content_hash", "question_key"),
                name="uniq_question_revision_hash_key",
            ),
        ]

    @property
    def answer_text(self) -> str:
        options = self.options or []
        if 0 <= self.answer_index < len(options):
            return options[self.answer_index]
        return ""

    def __str__(self) -> str:
        return f"Q {self.pk} ({self.difficulty})"


class QuestionTagLink(models.Model):
    """Adaptive selection groups questions by concept tag."""

    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name="tag_link")
    tag = models.ForeignKey("ai_classroom.Tag", on_delete=models.SET_NULL, null=True, related_name="questions")
