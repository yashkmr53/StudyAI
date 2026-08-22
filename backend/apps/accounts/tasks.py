"""Celery tasks for accounts (B8 monthly budget reset)."""
import logging

from config.celery import app
from django.utils import timezone

logger = logging.getLogger(__name__)


@app.task
def reset_monthly_budgets():
    """Reset monthly token/cost budgets for all profiles (1st of month 00:00 UTC)."""
    from apps.accounts.models import UserProfile

    now = timezone.now()
    reset_count = 0
    for profile in UserProfile.objects.iterator():
        if profile.budget_reset_date and profile.budget_reset_date < now:
            profile.current_month_token_usage = 0
            profile.current_month_cost_usd = 0
            profile.budget_reset_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + \
                timezone.timedelta(days=32)
            profile.budget_reset_date = profile.budget_reset_date.replace(day=1)
            profile.save(update_fields=[
                "current_month_token_usage",
                "current_month_cost_usd",
                "budget_reset_date",
            ])
            reset_count += 1
    if reset_count:
        logger.info("Reset monthly budgets for %s profiles", reset_count)
    return reset_count