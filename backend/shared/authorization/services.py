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
