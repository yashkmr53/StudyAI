"""Revision overview / goals / plans endpoints (architecture §58, §60)."""
from datetime import date

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.profiles.models import Profile
from apps.revision.models import RevisionGoal
from apps.revision.services import RevisionPlanningService
from apps.subjects.models import Subject


class GoalInSerializer(serializers.Serializer):
    subject = serializers.UUIDField(required=False, allow_null=True)
    target_date = serializers.DateField()
    hours_per_week = serializers.FloatField(required=False, allow_null=True, min_value=0)


class RevisionOverviewView(APIView):
    """GET /api/v1/revision/overview — per-tag mastery summary."""

    def get(self, request):
        profile = Profile.objects.filter(user=request.user).first()
        return Response(RevisionPlanningService.overview(profile))


class RevisionGoalsView(APIView):
    """POST /api/v1/revision/goals — create a goal (§58)."""

    def post(self, request):
        serializer = GoalInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        subject = None
        if data.get("subject"):
            try:
                subject = Subject.objects.get(pk=data["subject"], profile__user=request.user)
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this user.")

        profile = Profile.objects.filter(user=request.user).first()
        goal = RevisionGoal.objects.create(
            profile=profile,
            subject=subject,
            target_date=data["target_date"],
            hours_per_week=data.get("hours_per_week"),
        )
        return Response({
            "id": str(goal.pk),
            "subject": str(goal.subject_id) if goal.subject_id else None,
            "target_date": goal.target_date.isoformat(),
            "hours_per_week": goal.hours_per_week,
        }, status=201)

    def get(self, request):
        profile = Profile.objects.filter(user=request.user).first()
        goals = RevisionGoal.objects.filter(profile=profile)
        return Response({"results": [
            {
                "id": str(g.pk),
                "subject": str(g.subject_id) if g.subject_id else None,
                "target_date": g.target_date.isoformat(),
                "hours_per_week": g.hours_per_week,
            }
            for g in goals
        ]})


class RevisionPlansView(APIView):
    """GET /api/v1/revision/plans?subject={uuid}&target_date=YYYY-MM-DD — computed plan."""

    def get(self, request):
        profile = Profile.objects.filter(user=request.user).first()
        subject = None
        if request.query_params.get("subject"):
            try:
                subject = Subject.objects.get(
                    pk=request.query_params["subject"], profile__user=request.user
                )
            except Subject.DoesNotExist:
                from shared.exceptions import ValidationError

                raise ValidationError("Unknown subject for this user.")

        from datetime import timedelta
        from django.utils.dateparse import parse_date

        raw_target = request.query_params.get("target_date")
        if raw_target:
            target = parse_date(raw_target)
            if target is None:
                from shared.exceptions import ValidationError

                raise ValidationError("target_date must be YYYY-MM-DD.")
        else:
            target = date.today() + timedelta(days=14)
        hours = request.query_params.get("hours")

        plan = RevisionPlanningService.build_plan(profile, subject, target)
        return Response({**plan, "hours_per_week": float(hours) if hours else None})
