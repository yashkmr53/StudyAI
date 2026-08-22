"""Daily AI budget enforcement (architecture §21/§74).

Graceful degradation: when the per-profile daily budget is exhausted,
enrich/chat return 429 RATE_LIMITED; NoteSpace and source data remain
fully available. Budget counts enrich jobs + assistant chat messages
per profile per UTC day; once a live LLM lands, ProviderCallLog rows
become the spend proxy.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.chat.models import ChatMessage
from apps.jobs.models import Job


def _budget() -> int | None:
    value = getattr(settings, "AI_DAILY_BUDGET_PER_PROFILE", None)
    return int(value) if value else None


def ai_generations_today(profile_id) -> int:
    since = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return Job.objects.filter(
        Q(job_type="enrich", profile_id=profile_id, created_at__gte=since)
    ).count() + ChatMessage.objects.filter(
        session__profile_id=profile_id,
        role=ChatMessage.Role.ASSISTANT,
        created_at__gte=since,
    ).count()


def assert_within_budget(profile_id) -> None:
    from shared.exceptions import RateLimited

    budget = _budget()
    if budget is None:
        return
    if ai_generations_today(profile_id) >= budget:
        raise RateLimited("Daily AI budget exhausted for this profile; try again tomorrow.")
