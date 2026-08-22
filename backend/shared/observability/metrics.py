"""Lightweight metrics registry (§25) + request timing + Prometheus metrics.

Thread-safe in-process counters and a capped latency sample. The /status
endpoint (staff-only) exposes aggregates; per-request duration is logged
with the request id. Prometheus metrics are exposed via /metrics endpoint.
"""
import threading
import time
from collections import deque

from django.conf import settings

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

_lock = threading.Lock()
_latencies: deque = deque(maxlen=2000)  # last N request durations (ms)
_counters: dict[str, int] = {}

# Prometheus metrics (only initialized if django-prometheus is available)
_prom_metrics = {}


def _init_prometheus_metrics():
    """Initialize Prometheus metrics lazily."""
    global _prom_metrics
    if not PROMETHEUS_AVAILABLE or _prom_metrics:
        return

    _prom_metrics = {
        "ocr_fallback_total": Counter(
            "ocr_fallback_total",
            "Total number of OCR fallback attempts",
            ["provider", "reason"],
        ),
        "schema_validation_failure_total": Counter(
            "schema_validation_failure_total",
            "Total number of schema validation failures",
            ["endpoint", "field"],
        ),
        "retrieval_latency_seconds": Histogram(
            "retrieval_latency_seconds",
            "Retrieval latency in seconds",
            ["query_type"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        ),
        "evaluation_score": Gauge(
            "evaluation_score",
            "Evaluation score for various metrics",
            ["metric", "dataset"],
        ),
        "product_usage_total": Counter(
            "product_usage_total",
            "Total product usage events",
            ["feature", "action"],
        ),
    }


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


# Public API for Prometheus metrics
def ocr_fallback_inc(provider: str, reason: str) -> None:
    """Increment OCR fallback counter."""
    if PROMETHEUS_AVAILABLE:
        _init_prometheus_metrics()
        _prom_metrics["ocr_fallback_total"].labels(provider=provider, reason=reason).inc()
    incr(f"ocr_fallback.{provider}.{reason}")


def schema_validation_failure_inc(endpoint: str, field: str) -> None:
    """Increment schema validation failure counter."""
    if PROMETHEUS_AVAILABLE:
        _init_prometheus_metrics()
        _prom_metrics["schema_validation_failure_total"].labels(endpoint=endpoint, field=field).inc()
    incr(f"schema_validation_failure.{endpoint}.{field}")


def retrieval_latency_observe(query_type: str, latency_seconds: float) -> None:
    """Observe retrieval latency."""
    if PROMETHEUS_AVAILABLE:
        _init_prometheus_metrics()
        _prom_metrics["retrieval_latency_seconds"].labels(query_type=query_type).observe(latency_seconds)
    incr(f"retrieval_latency.{query_type}")


def evaluation_score_set(metric: str, dataset: str, value: float) -> None:
    """Set evaluation score gauge."""
    if PROMETHEUS_AVAILABLE:
        _init_prometheus_metrics()
        _prom_metrics["evaluation_score"].labels(metric=metric, dataset=dataset).set(value)
    incr(f"evaluation_score.{metric}.{dataset}")


def product_usage_inc(feature: str, action: str) -> None:
    """Increment product usage counter."""
    if PROMETHEUS_AVAILABLE:
        _init_prometheus_metrics()
        _prom_metrics["product_usage_total"].labels(feature=feature, action=action).inc()
    incr(f"product_usage.{feature}.{action}")


def get_prometheus_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not available\n"
    _init_prometheus_metrics()
    return generate_latest()


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
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response


# Prometheus metrics view
class PrometheusMetricsView:
    """View for /metrics endpoint."""

    def __call__(self, request):
        from django.http import HttpResponse
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", False):
            return HttpResponse("Metrics disabled", status=404)
        return HttpResponse(get_prometheus_metrics(), content_type=CONTENT_TYPE_LATEST)