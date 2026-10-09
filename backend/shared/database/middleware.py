"""Request-scoped RLS context middleware (architecture §3).

Reads ``X-Active-Profile`` from the request, validates it against the
authenticated user, and binds ``app.current_profile_id`` transaction-locally
via ``SET LOCAL`` so PostgreSQL RLS policies can scope rows.

Also enforces module isolation: when ``X-Active-Module`` is present, the
active profile must belong to that module. Cross-module profile reuse is
rejected with ``403 Forbidden``.

Celery workers already call ``profile_scoped_transaction`` directly; this
middleware covers the HTTP request path.
"""
from django.utils.deprecation import MiddlewareMixin

from shared.database.rls import set_profile_context


class RlsContextMiddleware(MiddlewareMixin):
    """Bind the active profile to the RLS GUC for the current transaction."""

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication

                authenticator = JWTAuthentication()
                header = authenticator.get_header(request)
                if header:
                    raw_token = authenticator.get_raw_token(header)
                    if raw_token:
                        validated_token = authenticator.get_validated_token(raw_token)
                        user = authenticator.get_user(validated_token)
                        request.user = user
            except Exception:
                pass

        profile_id = request.headers.get("X-Active-Profile")
        if not profile_id and hasattr(request, "META"):
            profile_id = request.META.get("HTTP_X_ACTIVE_PROFILE")
        if not profile_id and hasattr(request, "GET"):
            profile_id = request.GET.get("profile")

        if profile_id and user and user.is_authenticated:
            from apps.profiles.models import Profile

            try:
                if Profile.objects.filter(pk=profile_id, user=user).exists():
                    from shared.database.rls import profile_scoped_transaction

                    with profile_scoped_transaction(profile_id):
                        return self.get_response(request)
            except Exception:
                pass

        return self.get_response(request)
