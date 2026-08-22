"""Health + internal status endpoints (architecture §25, §75).

/healthz — liveness: process up.
/readyz   — readiness: DB roundtrip.
/api/v1/status — staff-only aggregates: jobs by status/type, dead-letters,
                 retryable backlog, provider usage, citation distribution,
                 request latency percentiles (§25 list).
/metrics   — Prometheus metrics endpoint (§25, E).
"""
from django.conf import settings
from django.db import connection
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.observability.metrics import get_prometheus_metrics


class HealthzView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class ReadyzView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_ok = True
        except Exception:
            db_ok = False
        return Response({"status": "ok" if db_ok else "degraded", "database": db_ok},
                        status=200 if db_ok else 503)


class StatusView(APIView):
    """Lightweight internal status page (staff only) — §25 metric list."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count
        from django.utils import timezone

        from apps.ai_classroom.models import CitationBlock
        from apps.audit.models import ProviderCallLog
        from apps.jobs.models import Job
        from apps.retrieval.services import combined_revision_hash  # noqa: F401 (import sanity)
        from shared.observability.metrics import snapshot

        day_ago = timezone.now() - timezone.timedelta(hours=24)
        by_status = dict(Job.objects.values_list("status").annotate(c=Count("id")))
        by_type = {f"{r['job_type']}:{r['status']}": r["c"] for r in Job.objects.values("job_type", "status").annotate(c=Count("id"))}
        retried_24h = Job.objects.filter(status="failed_retryable", created_at__gte=day_ago).count()
        created_24h = Job.objects.filter(created_at__gte=day_ago).count()

        provider_rows = ProviderCallLog.objects.values("provider", "success").annotate(c=Count("id"))
        provider_usage = {f"{r['provider']}:{'ok' if r['success'] else 'fail'}": r["c"] for r in provider_rows}

        citation_distribution = dict(
            CitationBlock.objects.values_list("verification_status").annotate(c=Count("id"))
        )

        snapshot_data = snapshot()
        payload = {
            "jobs": {
                "by_status": by_status,
                "by_type_status": by_type,
                "queue_depth": by_status.get("queued", 0),
                "dead_letter_count": by_status.get("failed_dead_letter", 0),
                "retryable_count": by_status.get("failed_retryable", 0),
                "created_last_24h": created_24h,
                "retried_last_24h": retried_24h,
            },
            "providers": {
                "usage": provider_usage,
                "ocr_fallback_rate": None,  # computed when real OCR lands (Phase 3+ providers mocked)
            },
            "citations": {"verification_distribution": citation_distribution},
            "requests": snapshot_data["requests"],
            "counters": snapshot_data["counters"],
            "database": {"vendor": connection.vendor},
        }
        return Response(payload)


class MetricsView(APIView):
    """Prometheus metrics endpoint."""

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        if not getattr(settings, "PROMETHEUS_METRICS_ENABLED", False):
            return Response({"detail": "Metrics disabled"}, status=404)
        from django.http import HttpResponse
        from prometheus_client import CONTENT_TYPE_LATEST
        return HttpResponse(get_prometheus_metrics(), content_type=CONTENT_TYPE_LATEST)
