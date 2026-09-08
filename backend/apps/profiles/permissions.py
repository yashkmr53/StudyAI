"""Module isolation permission (cross-module profile scoping).

Ensures that when ``X-Active-Module`` is supplied, the active profile
(from ``X-Active-Profile``) belongs to that module. Runs after DRF
authentication so ``request.user`` is available for token-based requests.
"""
from rest_framework import permissions

from apps.profiles.models import Profile


class ModuleIsolationPermission(permissions.BasePermission):
    """Reject requests that mix a profile with the wrong module.

    ``create`` is exempt everywhere. ``list`` is exempt only for viewsets
    whose serializer model is ``Profile`` so users can browse available
    profiles in any module. All other actions enforce module alignment.
    """

    def has_permission(self, request, view):
        from shared.exceptions import Forbidden

        if not hasattr(view, "action"):
            return True

        if view.action == "create":
            return True

        # Allow listing profiles regardless of module; the backend already
        # filters profiles by ``X-Active-Module`` in ``get_queryset``.
        if view.action == "list":
            serializer_class = getattr(view, "serializer_class", None)
            model = getattr(getattr(serializer_class, "Meta", None), "model", None)
            if model is not None and model.__name__ == "Profile":
                return True

        profile_id = request.headers.get("X-Active-Profile")
        module = request.headers.get("X-Active-Module")
        if not profile_id or not module:
            return True
        if module not in dict(Profile.Module.choices):
            return True
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return True
        try:
            profile = Profile.objects.get(pk=profile_id, user=user)
        except Profile.DoesNotExist:
            return True
        if profile.module != module:
            raise Forbidden("Profile does not belong to the requested module.")
        return True