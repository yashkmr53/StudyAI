"""Request-scoped RLS context middleware (architecture §3).

Reads ``X-Active-Profile`` from the request, validates it against the
authenticated user, and binds ``app.current_profile_id`` transaction-locally
via ``SET LOCAL`` so PostgreSQL RLS policies can scope rows.

Celery workers already call ``profile_scoped_transaction`` directly; this
middleware covers the HTTP request path.
"""
from django.utils.deprecation import MiddlewareMixin

from shared.database.rls import set_profile_context


class RlsContextMiddleware(MiddlewareMixin):
    """Bind the active profile to the RLS GUC for the current transaction."""

    def process_request(self, request):
        profile_id = request.headers.get("X-Active-Profile")
        if not profile_id:
            return None
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        from apps.profiles.models import Profile

        if not Profile.objects.filter(pk=profile_id, user=user).exists():
            return None
        set_profile_context(profile_id)
        return None
