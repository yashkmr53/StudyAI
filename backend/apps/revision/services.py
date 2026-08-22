"""Revision planner (architecture §58) — deterministic, no LLM.

Priorities (spec order): low mastery → high importance → approaching
assessment → recent failures → insufficiently assessed topics.
"""
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count

from apps.ai_classroom.models import DocumentTag, Tag
from apps.tests.models import MasteryScore, TestAttempt


def _weights() -> dict:
    return {
        "weakness": float(getattr(settings, "PLANNER_W_WEAKNESS", 0.45)),
        "urgency": float(getattr(settings, "PLANNER_W_URGENCY", 0.25)),
        "failures": float(getattr(settings, "PLANNER_W_FAILURES", 0.20)),
        "insufficient": float(getattr(settings, "PLANNER_W_INSUFFICIENT", 0.10)),
    }


class RevisionPlanningService:
    @staticmethod
    def overview(profile):
        """Per-tag mastery summary; tags linked to the profile's documents
        without a mastery row are reported as not_assessed."""
        linked_tags = (
            Tag.objects.filter(document_tags__document__profile=profile)
            .annotate(document_count=Count("document_tags", distinct=True))
            .distinct()
        )
        scores = {m.tag_id: m for m in MasteryScore.objects.filter(profile=profile).select_related("tag")}
        rows = []
        assessed = 0
        for tag in linked_tags:
            m = scores.get(tag.pk)
            status = RevisionPlanningService.mastery_status(m)
            if status != "not_assessed":
                assessed += 1
            rows.append({
                "tag_id": str(tag.pk),
                "stable_key": tag.stable_key,
                "display_name": tag.display_name,
                "status": status,
                "mastery": round(m.mastery, 4) if m else None,
                "attempt_count": m.attempt_count if m else 0,
                "last_assessed_at": m.last_assessed_at if m else None,
            })
        rows.sort(key=lambda r: (r["status"] == "not_assessed", -(r["mastery"] or 0)))
        return {
            "tags": rows,
            "assessed_count": assessed,
            "not_assessed_count": len(rows) - assessed,
        }

    @staticmethod
    def mastery_status(m):
        from apps.tests.services import WEAK_THRESHOLD, STRONG_THRESHOLD, MasteryScoringService

        return MasteryScoringService.mastery_status(m)

    @staticmethod
    def build_plan(profile, subject, target_date) -> dict:
        """Deterministic daily plan until target_date (max 14 days horizon),
        weakest / most urgent tags first."""
        today = date.today()
        days_left = max(1, (target_date - today).days)
        horizon = min(days_left, 14)

        tag_qs = Tag.objects.all()
        if subject is not None:
            tag_qs = tag_qs.filter(subject=subject)
        linked = Tag.objects.filter(document_tags__document__profile=profile)
        candidate_ids = set(tag_qs.values_list("id", flat=True)) & set(linked.values_list("id", flat=True))
        candidates = []
        cutoff = timezone_now() - timedelta(days=14)

        weights = _weights()
        urgency = min(1.0, days_left / 14) if days_left <= 14 else 0.2

        for tag in Tag.objects.filter(id__in=candidate_ids).select_related("subject"):
            m = MasteryScore.objects.filter(profile=profile, tag=tag).first()
            assessed = m is not None and m.attempt_count > 0
            weakness = (1.0 - m.mastery) if assessed else 0.55  # insufficiently assessed: mid priority
            recent_failures = TestAttempt.objects.filter(
                test__profile=profile,
                question__tag_link__tag=tag,
                correct=False,
                answered_at__gte=cutoff,
            ).count()
            failure_score = min(1.0, recent_failures / 5.0)
            insufficient = 0.0 if assessed else 1.0
            priority = (
                weights["weakness"] * weakness
                + weights["urgency"] * urgency
                + weights["failures"] * failure_score
                + weights["insufficient"] * insufficient
            )
            candidates.append({
                "tag_id": str(tag.pk),
                "display_name": tag.display_name,
                "status": RevisionPlanningService.mastery_status(m),
                "priority": round(priority, 4),
            })

        candidates.sort(key=lambda c: (-c["priority"], c["display_name"]))
        sessions_per_day = 2
        schedule = []
        for day_offset in range(horizon):
            day = today + timedelta(days=day_offset)
            items = []
            for slot in range(sessions_per_day):
                idx = (day_offset * sessions_per_day + slot) % max(1, len(candidates))
                if candidates:
                    items.append(candidates[idx]["display_name"])
            schedule.append({"date": day.isoformat(), "focus": sorted(set(items))})

        return {
            "target_date": target_date.isoformat(),
            "days_left": days_left,
            "priorities": candidates[:10],
            "schedule": schedule,
        }


def timezone_now():
    from django.utils import timezone

    return timezone.now()
