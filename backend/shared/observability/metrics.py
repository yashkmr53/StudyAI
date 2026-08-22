"""Lightweight metrics registry (§25) + request timing.

Thread-safe in-process counters and a capped latency sample. The /status
endpoint (staff-only) exposes aggregates; per-request duration is logged
with the request id. This is deliberately simple for v1 — no external
metrics pipeline.
"""
import threading
import time
from collections import deque

_lock = threading.Lock()
_latencies: deque = deque(maxlen=2000)  # last N request durations (ms)
_counters: dict[str, int] = {}


def incr(name: str, by: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + by


def observe_latency_ms(ms: float) -> None:
    with _lock:
        _latencies.append(round(ms, 1))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def snapshot() -> dict:
    with _lock:
        lats = list(_latencies)
        counters = dict(_counters)
    return {
        "requests": {
            "total": sum(1 for _ in lats),
            "p50_ms": percentile(lats, 50),
            "p95_ms": percentile(lats, 95),
            "p99_ms": percentile(lats, 99),
        },
        "counters": counters,
    }


class TimingMiddleware:
    """Records per-request duration; attaches X-Duration-Ms header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        observe_latency_ms(duration_ms)
        response["X-Duration-Ms"] = str(duration_ms)
        path = request.path
        if path.startswith("/api/"):
            incr(f"requests.{request.method}.{path.rstrip('/')}")
        return response


class SecurityHeadersMiddleware:
    """Baseline security headers on every response (§23)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
