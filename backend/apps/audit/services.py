"""Audit service — explicit, non-blocking audit writes (§23)."""
import logging

from django.db import transaction

from apps.audit.models import AuditLog

logger = logging.getLogger(__name__)


def audit(*, actor=None, action: str, resource_type: str = "", resource_id: str = "",
          request=None, metadata: dict | None = None) -> None:
    """Record an administrative/audit event. Never raises into caller flow."""
    try:
        ip = None
        if request is not None:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
        with transaction.atomic():
            AuditLog.objects.create(
                actor=actor if getattr(actor, "pk", None) else None,
                actor_email=getattr(actor, "email", "") or "",
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id or ""),
                metadata=metadata or {},
                ip_address=ip,
            )
    except Exception:  # noqa: BLE001 — audit failures must never break user flows
        logger.warning("Audit write failed for action=%s", action, exc_info=True)
