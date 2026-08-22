"""Adaptive test endpoints (architecture §55–56, §60)."""
import json

from django.db import transaction
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.questions.models import Question
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.tests.models import TestAttempt, TestInstance
from apps.tests.services import MasteryScoringService, TestGenerationService


class AttemptInSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_index = serializers.IntegerField(min_value=0)
    confidence = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=1)


def _serialize_test(test: TestInstance, include_questions: bool = True) -> dict:
    attempts = {a.question_id: a for a in TestAttempt.objects.filter(test=test)}
    data = {
        "id": str(test.pk),
        "subject": str(test.subject_id) if test.subject_id else None,
        "type": test.type,
        "created_at": test.created_at,
        "question_count": test.test_questions.count(),
    }
    if include_questions:
        questions = []
        for tq in test.test_questions.select_related("question").order_by("order"):
            q = tq.question
            attempt = attempts.get(q.pk)
            item = {
                "id": str(q.pk),
                "difficulty": q.difficulty,
                "prompt": q.prompt,
                "options": q.options,
                "answered": attempt is not None,
                "selected_index": attempt.selected_index if attempt else None,
                "correct": attempt.correct if attempt else None,
            }
            questions.append(item)
        data["questions"] = questions
    return data


class TestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return TestInstance.objects.filter(profile__user=self.request.user)

    def create(self, request):
        subject = None
        subject_id = request.data.get("subject")
        if subject_id:
            try:
                subject = Subject.objects.get(pk=subject_id, profile__user=request.user)
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this user.")

        profile = Profile.objects.filter(user=request.user).first()
        try:
            num = int(request.data.get("num_questions", 5))
        except (TypeError, ValueError):
            num = 5
        test = TestGenerationService.build_test(
            profile, subject=subject, num_questions=max(1, min(num, 20)),
            type_=TestInstance.Type.PRACTICE,
        )
        return Response(_serialize_test(test), status=201)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        results = [_serialize_test(t, include_questions=False) for t in qs]
        return Response({"count": len(results), "results": results})

    def retrieve(self, request, *args, **kwargs):
        test = self.get_object()
        return Response(_serialize_test(test))

    @action(detail=True, methods=["post"])
    def attempts(self, request, pk=None):
        from shared.exceptions import IdempotencyConflict, ValidationError

        test = self.get_object()
        serializer = AttemptInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = Question.objects.filter(
            pk=serializer.validated_data["question_id"],
            test_questions__test=test,
        ).first()
        if question is None:
            raise ValidationError("Question does not belong to this test.")

        existing = TestAttempt.objects.filter(test=test, question=question).first()
        if existing:
            raise IdempotencyConflict("Question already attempted in this test.")

        selected = serializer.validated_data["selected_index"]
        correct = selected == question.answer_index
        confidence = serializer.validated_data.get("confidence")

        with transaction.atomic():
            attempt = TestAttempt.objects.create(
                test=test,
                question=question,
                selected_index=selected,
                correct=correct,
                confidence=confidence,
            )
            mastery = MasteryScoringService.record_attempt(
                test.profile, question, correct=correct, confidence=confidence
            )

        payload = {
            "attempt": {
                "id": str(attempt.pk),
                "correct": attempt.correct,
                "answer_index": question.answer_index,
                "answered_at": attempt.answered_at,
            },
            "mastery": (
                {"tag": mastery.tag.stable_key, "value": round(mastery.mastery, 4),
                 "status": MasteryScoringService.mastery_status(mastery)}
                if mastery
                else None
            ),
        }
        return Response(payload, status=201)
