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
    """Throttle that atomically reserves monthly AI budget and links settlement (B8, T9)."""

    scope = "ai"

    def allow_request(self, request, view):
        # First check standard rate limit
        if not super().allow_request(request, view):
            return False

        # Reserve estimated monthly budget atomically if authenticated
        if request.user and request.user.is_authenticated:
            from apps.accounts.services.budget import (
                BudgetExceeded,
                BudgetService,
                set_active_reservation,
                set_active_reservation_id,
            )
            from shared.exceptions import RateLimited

            estimated_tokens = 500  # default estimate
            estimated_cost = Decimal("0.001")  # default estimate

            try:
                reservation = BudgetService.reserve(request.user, estimated_tokens, estimated_cost)
                raw_request = getattr(request, "_request", request)
                raw_request._budget_reservation = reservation
                set_active_reservation(reservation)
                set_active_reservation_id(reservation.reservation_id)
            except BudgetExceeded as exc:
                raise RateLimited(details={
                    "budget_type": exc.budget_type,
                    "limit": str(exc.limit),
                    "current": str(exc.current),
                    "reset_date": None,
                })

        return True


class BudgetSettlementMiddleware:
    """Settle or refund any request-scoped AI budget reservation upon response/error (T9)."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        from asgiref.sync import iscoroutinefunction, markcoroutinefunction

        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    @staticmethod
    def _settle_or_release(request, *, status_code: int = 500, errored: bool = False) -> None:
        from apps.accounts.services.budget import BudgetService

        reservation = getattr(request, "_budget_reservation", None)
        if reservation is None or getattr(request, "_budget_reservation_deferred", False):
            return
        if errored or status_code >= 400:
            BudgetService.release(reservation)
        else:
            BudgetService.settle_from_logs(reservation)

    def __call__(self, request):
        from asgiref.sync import iscoroutinefunction

        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)

        from apps.accounts.services.budget import (
            _active_reservation,
            _active_reservation_id,
            set_active_reservation,
            set_active_reservation_id,
        )

        token = set_active_reservation_id(None)
        res_token = set_active_reservation(None)
        try:
            response = self.get_response(request)
        except Exception:
            self._settle_or_release(request, errored=True)
            raise
        else:
            self._settle_or_release(request, status_code=getattr(response, "status_code", 500))
            return response
        finally:
            _active_reservation_id.reset(token)
            _active_reservation.reset(res_token)

    async def __acall__(self, request):
        from asgiref.sync import sync_to_async
        from apps.accounts.services.budget import (
            _active_reservation,
            _active_reservation_id,
            set_active_reservation,
            set_active_reservation_id,
        )

        token = set_active_reservation_id(None)
        res_token = set_active_reservation(None)
        try:
            response = await self.get_response(request)
        except Exception:
            await sync_to_async(self._settle_or_release, thread_sensitive=True)(request, errored=True)
            raise
        else:
            await sync_to_async(self._settle_or_release, thread_sensitive=True)(
                request, status_code=getattr(response, "status_code", 500)
            )
            return response
        finally:
            _active_reservation_id.reset(token)
            _active_reservation.reset(res_token)


LiveScopedRateThrottle = LiveSettingsScopedRateThrottle
