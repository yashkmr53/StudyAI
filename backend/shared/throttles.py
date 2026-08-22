"""Throttles whose rates are read live from settings (§23).

DRF's ScopedRateThrottle binds DEFAULT_THROTTLE_RATES to the class at
import time, which makes per-environment overrides (and test overrides)
invisible. This subclass resolves the rates dict dynamically.
"""
from rest_framework.throttling import ScopedRateThrottle


class LiveSettingsScopedRateThrottle(ScopedRateThrottle):
    @property
    def THROTTLE_RATES(self):
        from django.conf import settings

        return settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})

    def get_rate(self):
        from django.conf import settings

        if not getattr(settings, "RATE_LIMITING_ENABLED", True):
            return None  # DRF: None ⇒ never throttled
        return super().get_rate()


LiveScopedRateThrottle = LiveSettingsScopedRateThrottle
