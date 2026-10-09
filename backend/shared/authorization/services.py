"""ProfileAuthorizationService (architecture §3, §65).

Application-layer defense: client-supplied profile IDs are never trusted.
The authenticated user's ownership is verified server-side before any
profile-scoped operation proceeds. Database RLS is the second layer.
"""
from shared.exceptions import Forbidden, ResourceNotFound


class ProfileAuthorizationService:
    @staticmethod
    def ensure_profile_access(user, profile) -> None:
        if profile is None:
            raise ResourceNotFound("Profile not found.")
        if profile.user_id != user.pk:
            raise Forbidden()

    @staticmethod
    def get_owned_profile(user, profile_id):
        from apps.profiles.models import Profile

        try:
            profile = Profile.objects.get(pk=profile_id)
        except (Profile.DoesNotExist, ValueError, TypeError):
            raise ResourceNotFound("Profile not found.")
        ProfileAuthorizationService.ensure_profile_access(user, profile)
        return profile

    @staticmethod
    def ensure_subject_access(user, subject) -> None:
        ProfileAuthorizationService.ensure_profile_access(user, subject.profile)

    @staticmethod
    def get_active_profile(request):
        if not hasattr(request, "user"):
            return None
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        if hasattr(request, "_cached_active_profile") and request._cached_active_profile is not None:
            return request._cached_active_profile

        profile_id = None
        if hasattr(request, "headers"):
            profile_id = request.headers.get("X-Active-Profile") or request.headers.get("X-Profile-ID")
        if not profile_id and hasattr(request, "META"):
            profile_id = request.META.get("HTTP_X_ACTIVE_PROFILE") or request.META.get("HTTP_X_PROFILE_ID")
        if not profile_id and hasattr(request, "query_params"):
            profile_id = request.query_params.get("profile")

        from apps.profiles.models import Profile

        profile = None
        if profile_id:
            try:
                profile = Profile.objects.get(pk=profile_id, user=user)
            except (Profile.DoesNotExist, ValueError, TypeError):
                profile = None
        if not profile and not profile_id:
            # If no profile ID was explicitly specified, resolve only if user has exactly one profile
            user_profiles = list(Profile.objects.filter(user=user)[:2])
            if len(user_profiles) == 1:
                profile = user_profiles[0]
            else:
                profile = None

        request._cached_active_profile = profile
        return profile

    @staticmethod
    def require_active_profile(request):
        profile = ProfileAuthorizationService.get_active_profile(request)
        if not profile:
            from shared.exceptions import ValidationError
            raise ValidationError("Active profile context is required. Please provide a valid X-Active-Profile header.")
        return profile


from django.http import HttpRequest
from rest_framework.request import Request

HttpRequest.profile = property(lambda self: ProfileAuthorizationService.get_active_profile(self))
Request.profile = property(lambda self: ProfileAuthorizationService.get_active_profile(self))
