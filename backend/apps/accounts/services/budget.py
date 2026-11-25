"""Unified, atomic AI budget enforcement & reserve/settle service (B8, T9).

Reconciles:
- Monthly atomic token + USD cost budgets on UserProfile via conditional F() SQL UPDATE
  with reserve -> settle (actual ProviderCallLog usage) -> release (on error).
- Optional legacy daily per-profile generation count limit (AI_DAILY_BUDGET_PER_PROFILE).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
import logging
import uuid
from typing import Any, Optional

from django.conf import settings
from django.db.models import Case, DecimalField, F, IntegerField, Q, Sum, Value, When
from django.utils import timezone

logger = logging.getLogger(__name__)

_active_reservation_id: ContextVar[Optional[str]] = ContextVar("_active_reservation_id", default=None)
_active_reservation: ContextVar[Optional["BudgetReservation"]] = ContextVar("_active_reservation", default=None)


def get_active_reservation_id() -> Optional[str]:
    return _active_reservation_id.get()


def get_active_reservation() -> Optional["BudgetReservation"]:
    return _active_reservation.get()


def set_active_reservation_id(reservation_id: Optional[str]):
    return _active_reservation_id.set(reservation_id)


def set_active_reservation(reservation: Optional["BudgetReservation"]):
    return _active_reservation.set(reservation)


@contextmanager
def active_reservation_context(reservation_id: Optional[str]):
    token = _active_reservation_id.set(reservation_id)
    try:
        yield
    finally:
        _active_reservation_id.reset(token)


@dataclass
class BudgetReservation:
    reservation_id: str
    user_id: Any
    profile_pk: int
    reserved_tokens: int
    reserved_cost: Decimal
    settled: bool = False
    released: bool = False

    def to_dict(self) -> dict:
        return {
            "reservation_id": self.reservation_id,
            "user_id": str(self.user_id),
            "profile_pk": self.profile_pk,
            "reserved_tokens": self.reserved_tokens,
            "reserved_cost": str(self.reserved_cost),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Optional["BudgetReservation"]:
        if not data or not isinstance(data, dict) or not data.get("profile_pk"):
            return None
        return cls(
            reservation_id=data["reservation_id"],
            user_id=data["user_id"],
            profile_pk=int(data["profile_pk"]),
            reserved_tokens=int(data.get("reserved_tokens", 0)),
            reserved_cost=Decimal(str(data.get("reserved_cost", "0"))),
        )


class BudgetExceeded(Exception):
    """Raised when a budget limit is exceeded."""

    def __init__(self, budget_type: str, limit: int | Decimal, current: int | Decimal):
        self.budget_type = budget_type
        self.limit = limit
        self.current = current
        super().__init__(
            f"{budget_type} budget exceeded: {current} / {limit}"
        )


def _next_month_start(now):
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


class BudgetService:
    """Unified atomic reserve/settle/release monthly budgets + optional daily profile cap."""

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
        if created and not profile.budget_reset_date:
            next_reset = _next_month_start(timezone.now())
            UserProfile.objects.filter(pk=profile.pk, budget_reset_date__isnull=True).update(
                budget_reset_date=next_reset
            )
            profile.refresh_from_db()
        return profile

    @staticmethod
    def _reset_if_needed(profile):
        """Atomically reset monthly counters if budget_reset_date has passed."""
        from apps.accounts.models import UserProfile

        now = timezone.now()
        if profile.budget_reset_date and profile.budget_reset_date <= now:
            next_reset = _next_month_start(now)
            updated = UserProfile.objects.filter(
                pk=profile.pk,
                budget_reset_date__lte=now,
            ).update(
                current_month_token_usage=0,
                current_month_cost_usd=Decimal("0"),
                budget_reset_date=next_reset,
            )
            if updated:
                profile.refresh_from_db()

    @classmethod
    def reserve(
        cls,
        user,
        tokens: int,
        cost_usd: Decimal | float | str,
        *,
        reservation_id: Optional[str] = None,
    ) -> BudgetReservation:
        """Atomically reserve estimated tokens & cost using conditional F() UPDATE."""
        from apps.accounts.models import UserProfile

        est_tokens = max(0, int(tokens))
        est_cost = Decimal(str(cost_usd))

        profile = cls._get_or_create_profile(user)
        cls._reset_if_needed(profile)

        updated = UserProfile.objects.filter(
            pk=profile.pk,
            current_month_token_usage__lte=F("monthly_token_budget") - est_tokens,
            current_month_cost_usd__lte=F("monthly_cost_budget_usd") - est_cost,
        ).update(
            current_month_token_usage=F("current_month_token_usage") + est_tokens,
            current_month_cost_usd=F("current_month_cost_usd") + est_cost,
        )

        if updated == 0:
            profile.refresh_from_db()
            new_tokens = profile.current_month_token_usage + est_tokens
            if new_tokens > profile.monthly_token_budget:
                logger.warning(
                    "Token budget exceeded for user %s: %s + %s > %s",
                    user.id, profile.current_month_token_usage, est_tokens, profile.monthly_token_budget,
                )
                raise BudgetExceeded("token", profile.monthly_token_budget, new_tokens)

            new_cost = profile.current_month_cost_usd + est_cost
            logger.warning(
                "Cost budget exceeded for user %s: %s + %s > %s",
                user.id, profile.current_month_cost_usd, est_cost, profile.monthly_cost_budget_usd,
            )
            raise BudgetExceeded("cost", profile.monthly_cost_budget_usd, new_cost)

        return BudgetReservation(
            reservation_id=reservation_id or uuid.uuid4().hex,
            user_id=user.pk,
            profile_pk=profile.pk,
            reserved_tokens=est_tokens,
            reserved_cost=est_cost,
        )

    @classmethod
    def _apply_delta(cls, profile_pk: int, token_delta: int, cost_delta: Decimal) -> None:
        from apps.accounts.models import UserProfile

        if token_delta == 0 and cost_delta == 0:
            return

        update_kwargs: dict[str, Any] = {}
        if token_delta > 0:
            update_kwargs["current_month_token_usage"] = F("current_month_token_usage") + token_delta
        elif token_delta < 0:
            decrement = abs(token_delta)
            update_kwargs["current_month_token_usage"] = Case(
                When(current_month_token_usage__gte=decrement, then=F("current_month_token_usage") - decrement),
                default=Value(0),
                output_field=IntegerField(),
            )

        if cost_delta > 0:
            update_kwargs["current_month_cost_usd"] = F("current_month_cost_usd") + cost_delta
        elif cost_delta < 0:
            decrement_cost = abs(cost_delta)
            update_kwargs["current_month_cost_usd"] = Case(
                When(current_month_cost_usd__gte=decrement_cost, then=F("current_month_cost_usd") - decrement_cost),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )

        if update_kwargs:
            UserProfile.objects.filter(pk=profile_pk).update(**update_kwargs)

    @classmethod
    def settle(
        cls,
        reservation: Optional[BudgetReservation],
        actual_tokens: int,
        actual_cost: Decimal | float | str = Decimal("0"),
    ) -> None:
        """Adjust reserved usage by (actual - estimate) atomically."""
        if reservation is None or reservation.settled or reservation.released:
            return
        actual_tok = max(0, int(actual_tokens))
        actual_c = Decimal(str(actual_cost))
        token_delta = actual_tok - reservation.reserved_tokens
        cost_delta = actual_c - reservation.reserved_cost
        cls._apply_delta(reservation.profile_pk, token_delta, cost_delta)
        reservation.settled = True

    @classmethod
    def settle_from_logs(cls, reservation: Optional[BudgetReservation]) -> tuple[int, Decimal]:
        """Sum actual usage from ProviderCallLog for reservation_id and settle delta."""
        if reservation is None or reservation.settled or reservation.released:
            return (0, Decimal("0"))
        from apps.audit.models import ProviderCallLog

        logs = ProviderCallLog.objects.filter(
            metadata__reservation_id=reservation.reservation_id,
            success=True,
        )
        agg = logs.aggregate(
            sum_total=Sum("total_tokens"),
            sum_in=Sum("input_tokens"),
            sum_out=Sum("output_tokens"),
            sum_cost=Sum("estimated_cost_usd"),
        )
        total_tok = agg.get("sum_total")
        if total_tok is None:
            total_tok = (agg.get("sum_in") or 0) + (agg.get("sum_out") or 0)
        actual_cost = agg.get("sum_cost") or Decimal("0")
        cls.settle(reservation, int(total_tok or 0), actual_cost)
        return (int(total_tok or 0), Decimal(str(actual_cost)))

    @classmethod
    def release(cls, reservation: Optional[BudgetReservation]) -> None:
        """Refund a pending reservation if the AI call failed or was rejected."""
        if reservation is None or reservation.settled or reservation.released:
            return
        cls._apply_delta(
            reservation.profile_pk,
            -reservation.reserved_tokens,
            -reservation.reserved_cost,
        )
        reservation.released = True

    @classmethod
    def check_and_increment(cls, user, tokens: int, cost_usd: Decimal) -> BudgetReservation:
        """Backwards-compatible entry point delegating to atomic reserve()."""
        return cls.reserve(user, tokens, cost_usd)

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

    @staticmethod
    def ai_generations_today(profile_id) -> int:
        from apps.chat.models import ChatMessage
        from apps.jobs.models import Job

        since = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return Job.objects.filter(
            Q(job_type="enrich", profile_id=profile_id, created_at__gte=since)
        ).count() + ChatMessage.objects.filter(
            session__profile_id=profile_id,
            role=ChatMessage.Role.ASSISTANT,
            created_at__gte=since,
        ).count()

    @classmethod
    def assert_within_daily_budget(cls, profile_id) -> None:
        from shared.exceptions import RateLimited

        limit = getattr(settings, "AI_DAILY_BUDGET_PER_PROFILE", None)
        if not limit:
            return
        if cls.ai_generations_today(profile_id) >= int(limit):
            raise RateLimited("Daily AI budget exhausted for this profile; try again tomorrow.")