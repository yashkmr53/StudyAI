"""Throttles whose rates are read live from settings (§23).

DRF's ScopedRateThrottle binds DEFAULT_THROTTLE_RATES to the class at
import time, which makes per-environment overrides (and test overrides)
invisible. This subclass resolves the rates dict dynamically.

The throttle uses the 'throttle' cache alias (Redis-backed in production,
LocMemCache in dev) for distributed rate limiting (D3).
"""
from decimal import Decimal
from django.core.cache import caches
from rest_framework.throttling import ScopedRateThrottle


class LiveSettingsScopedRateThrottle(ScopedRateThrottle):
    cache = "throttle"  # Uses CACHES['throttle'] from settings (Redis in prod)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Resolve cache alias to actual cache backend
        if isinstance(self.cache, str):
            self.cache = caches[self.cache]

    @property
    def THROTTLE_RATES(self):
        from django.conf import settings

        return settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})

    def get_rate(self):
        from django.conf import settings

        if not getattr(settings, "RATE_LIMITING_ENABLED", True):
            return None  # DRF: None ⇒ never throttled
        return super().get_rate()


class AIBudgetThrottle(LiveSettingsScopedRateThrottle):
    """Throttle that also enforces monthly AI budget (B8)."""

    scope = "ai"

    def allow_request(self, request, view):
        # First check standard rate limit
        if not super().allow_request(request, view):
            return False

        # Then check monthly budget if authenticated
        if request.user and request.user.is_authenticated:
            from apps.accounts.services.budget import BudgetService, BudgetExceeded
            from shared.exceptions import RateLimited

            # Estimate tokens for this request (rough heuristic)
            estimated_tokens = 500  # default estimate
            estimated_cost = Decimal("0.001")  # default estimate

            try:
                BudgetService.check_and_increment(request.user, estimated_tokens, estimated_cost)
            except BudgetExceeded as exc:
                raise RateLimited(details={
                    "budget_type": exc.budget_type,
                    "limit": str(exc.limit),
                    "current": str(exc.current),
                    "reset_date": None,  # BudgetService doesn't expose this easily here
                })

        return True


LiveScopedRateThrottle = LiveSettingsScopedRateThrottle
