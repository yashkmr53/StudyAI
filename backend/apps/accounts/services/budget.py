"""Monthly AI budget enforcement (B8)."""
import logging
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when a budget limit is exceeded."""

    def __init__(self, budget_type: str, limit: int | Decimal, current: int | Decimal):
        self.budget_type = budget_type
        self.limit = limit
        self.current = current
        super().__init__(
            f"{budget_type} budget exceeded: {current} / {limit}"
        )


class BudgetService:
    """Check and increment per-profile monthly AI budgets."""

    @staticmethod
    def _get_or_create_profile(user):
        from apps.accounts.models import UserProfile

        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "monthly_token_budget": getattr(settings, "DEFAULT_MONTHLY_TOKEN_BUDGET", 100000),
                "monthly_cost_budget_usd": getattr(settings, "DEFAULT_MONTHLY_COST_BUDGET_USD", Decimal("50.00")),
            },
        )
        if created:
            profile.budget_reset_date = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timezone.timedelta(days=32)
            profile.budget_reset_date = profile.budget_reset_date.replace(day=1)
            profile.save(update_fields=["budget_reset_date"])
        return profile

    @staticmethod
    def _reset_if_needed(profile):
        """Reset counters if the reset date has passed."""
        now = timezone.now()
        if profile.budget_reset_date and profile.budget_reset_date <= now:
            profile.current_month_token_usage = 0
            profile.current_month_cost_usd = Decimal("0")
            # Next reset = 1st of next month
            if now.month == 12:
                next_reset = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_reset = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            profile.budget_reset_date = next_reset
            profile.save(update_fields=["current_month_token_usage", "current_month_cost_usd", "budget_reset_date"])

    @classmethod
    def check_and_increment(cls, user, tokens: int, cost_usd: Decimal) -> None:
        """
        Check if the request would exceed budgets; if not, increment usage.

        Raises:
            BudgetExceeded: if token or cost budget would be exceeded.
        """
        from apps.accounts.models import UserProfile

        profile = cls._get_or_create_profile(user)
        cls._reset_if_needed(profile)

        # Check token budget
        new_token_usage = profile.current_month_token_usage + tokens
        if new_token_usage > profile.monthly_token_budget:
            logger.warning(
                "Token budget exceeded for user %s: %s + %s > %s",
                user.id, profile.current_month_token_usage, tokens, profile.monthly_token_budget
            )
            raise BudgetExceeded("token", profile.monthly_token_budget, new_token_usage)

        # Check cost budget
        new_cost = profile.current_month_cost_usd + cost_usd
        if new_cost > profile.monthly_cost_budget_usd:
            logger.warning(
                "Cost budget exceeded for user %s: %s + %s > %s",
                user.id, profile.current_month_cost_usd, cost_usd, profile.monthly_cost_budget_usd
            )
            raise BudgetExceeded("cost", profile.monthly_cost_budget_usd, new_cost)

        # Increment atomically
        UserProfile.objects.filter(pk=profile.pk).update(
            current_month_token_usage=new_token_usage,
            current_month_cost_usd=new_cost,
        )

    @classmethod
    def get_remaining(cls, user) -> dict:
        """Get remaining budget for a user."""
        profile = cls._get_or_create_profile(user)
        cls._reset_if_needed(profile)
        return {
            "token_budget": profile.monthly_token_budget,
            "token_used": profile.current_month_token_usage,
            "token_remaining": max(0, profile.monthly_token_budget - profile.current_month_token_usage),
            "cost_budget_usd": float(profile.monthly_cost_budget_usd),
            "cost_used_usd": float(profile.current_month_cost_usd),
            "cost_remaining_usd": float(max(Decimal("0"), profile.monthly_cost_budget_usd - profile.current_month_cost_usd)),
            "reset_date": profile.budget_reset_date.isoformat() if profile.budget_reset_date else None,
        }