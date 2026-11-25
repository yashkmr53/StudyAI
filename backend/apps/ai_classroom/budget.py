"""Compatibility facade delegating per-profile daily cap to canonical BudgetService (T9)."""
from apps.accounts.services.budget import BudgetService


def ai_generations_today(profile_id) -> int:
    return BudgetService.ai_generations_today(profile_id)


def assert_within_budget(profile_id) -> None:
    BudgetService.assert_within_daily_budget(profile_id)
