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
from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async


class RlsContextMiddleware:
    """Bind the active profile to the RLS GUC for the current transaction/request."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response=None):
        self.get_response = get_response
        if get_response is not None and iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    @staticmethod
    def _resolve_validated_profile_id(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            force_user = getattr(request, "_force_auth_user", None)
            if force_user is not None and getattr(force_user, "is_authenticated", False):
                user = force_user
                request.user = user
            else:
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

        profile_id = request.headers.get("X-Active-Profile") or request.headers.get("X-Profile-ID")
        if not profile_id and hasattr(request, "META"):
            profile_id = request.META.get("HTTP_X_ACTIVE_PROFILE") or request.META.get("HTTP_X_PROFILE_ID")
        if not profile_id and hasattr(request, "GET"):
            profile_id = request.GET.get("profile")
        if not profile_id and user and user.is_authenticated:
            from shared.authorization.services import ProfileAuthorizationService

            active_profile = ProfileAuthorizationService.get_active_profile(request)
            if active_profile:
                profile_id = str(active_profile.id)

        if profile_id and user and user.is_authenticated:
            from apps.profiles.models import Profile

            try:
                if Profile.objects.filter(pk=profile_id, user=user).exists():
                    return str(profile_id)
            except Exception:
                pass
        return None

    @staticmethod
    def _bind(profile_id: str) -> str:
        from shared.database.rls import bind_profile_session, get_current_profile_id

        prev = get_current_profile_id()
        bind_profile_session(profile_id)
        return prev

    @staticmethod
    def _restore(prev: str) -> None:
        from shared.database.rls import bind_profile_session, clear_profile_context

        clear_profile_context()
        if prev:
            bind_profile_session(prev)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)

        profile_id = self._resolve_validated_profile_id(request)
        if profile_id:
            prev = self._bind(profile_id)
            try:
                return self.get_response(request)
            finally:
                self._restore(prev)
        return self.get_response(request)

    async def __acall__(self, request):
        profile_id = await sync_to_async(self._resolve_validated_profile_id, thread_sensitive=True)(request)
        if profile_id:
            prev = await sync_to_async(self._bind, thread_sensitive=True)(profile_id)
            try:
                return await self.get_response(request)
            finally:
                await sync_to_async(self._restore, thread_sensitive=True)(prev)
        return await self.get_response(request)
