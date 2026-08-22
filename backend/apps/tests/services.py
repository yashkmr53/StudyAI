"""Mastery scoring + adaptive test generation (architecture §17–18, §55–58).

MasteryScoringService: deterministic EMA update on attempts; tags without
attempts are not_assessed (no row), never zero.
TestGenerationService: deterministic priority ordering over eligible
questions — weakness first, then recency, then difficulty match.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.questions.models import Question
from apps.tests.models import MasteryScore, TestAttempt, TestInstance, TestQuestion

logger = logging.getLogger(__name__)

WEAK_THRESHOLD = 0.4
STRONG_THRESHOLD = 0.8
RECENCY_DAYS = 7


class MasteryScoringService:
    @staticmethod
    def mastery_status(score: "MasteryScore | None") -> str:
        if score is None or score.attempt_count == 0:
            return "not_assessed"
        if score.mastery >= STRONG_THRESHOLD:
            return "strong"
        if score.mastery >= WEAK_THRESHOLD:
            return "fair"
        return "weak"

    @staticmethod
    def get_or_create(profile, tag, subject=None) -> MasteryScore:
        return MasteryScore.objects.get_or_create(
            profile=profile,
            tag=tag,
            defaults={"subject": subject or getattr(tag, "subject", None)},
        )[0]

    @staticmethod
    @transaction.atomic
    def record_attempt(profile, question: Question, *, correct: bool, confidence: float | None) -> MasteryScore | None:
        """Single-transaction attempt scoring (§56). Returns updated row or
        None when the question has no tag to score against."""
        from apps.questions.models import QuestionTagLink

        link = getattr(question, "tag_link", None)
        tag = link.tag if link else None
        if tag is None:
            return None

        mastery = MasteryScoringService.get_or_create(profile, tag, subject=question.document.subject)
        conf = confidence if confidence is not None else 0.75
        old = mastery.mastery
        if correct:
            gain = (1.0 - old) * 0.4 * (0.5 + conf / 2.0)
            mastery.mastery = min(1.0, old + gain)
        else:
            penalty = 0.4 * (0.5 + (1.0 - conf) / 2.0)
            mastery.mastery = max(0.0, old - old * penalty)
        mastery.attempt_count += 1
        mastery.correct_count += 1 if correct else 0
        mastery.last_assessed_at = timezone.now()
        mastery.save()
        return mastery


class TestGenerationService:
    WEIGHT_WEAKNESS = 0.6
    WEIGHT_RECENCY = 0.25
    WEIGHT_DIFFICULTY = 0.15

    @staticmethod
    def _priority(question: Question, profile) -> float:
        from apps.ai_classroom.models import DocumentTag

        tag = None
        link = getattr(question, "tag_link", None)
        tag = link.tag if link else None
        if tag is None:
            dt = DocumentTag.objects.filter(document=question.document).select_related("tag").first()
            tag = dt.tag if dt else None

        score_row = MasteryScore.objects.filter(profile=profile, tag=tag).first() if tag else None
        mastery_value = score_row.mastery if score_row and score_row.attempt_count else 0.5  # neutral

        last_attempt = (
            TestAttempt.objects.filter(test__profile=profile, question=question)
            .order_by("-answered_at")
            .first()
        )
        if last_attempt is None:
            recency_bonus = 1.0
        else:
            days = (timezone.now() - last_attempt.answered_at).days
            recency_bonus = 1.0 if days >= RECENCY_DAYS else days / RECENCY_DAYS

        difficulty_bonus = 1.0 if question.difficulty == Question.Difficulty.MEDIUM else 0.5

        return (
            TestGenerationService.WEIGHT_WEAKNESS * (1.0 - mastery_value)
            + TestGenerationService.WEIGHT_RECENCY * recency_bonus
            + TestGenerationService.WEIGHT_DIFFICULTY * difficulty_bonus
        )

    @classmethod
    def build_test(cls, profile, *, subject=None, num_questions: int = 5, type_=TestInstance.Type.PRACTICE):
        qs = Question.objects.filter(
            document__profile__user=profile.user, stale=False
        ).select_related("document")
        if subject is not None:
            qs = qs.filter(document__subject=subject)

        scored = sorted(
            ((cls._priority(q, profile), str(q.pk), q) for q in qs),
            key=lambda t: (-t[0], t[1]),
        )
        selected = [q for _, _, q in scored[:num_questions]]

        with transaction.atomic():
            test = TestInstance.objects.create(profile=profile, subject=subject, type=type_)
            for order, q in enumerate(selected, start=1):
                TestQuestion.objects.create(test=test, question=q, order=order)
        return test
