"""Authentication endpoints (architecture §44.1, §60, §23).

Registration creates the User and a default Profile in one transaction and
issues an authenticated token pair. Login/logout are audit-logged; auth
endpoints carry a scoped rate throttle (§23 rate limiting).
"""
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from shared.throttles import LiveSettingsScopedRateThrottle as ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.models import User
from apps.accounts.serializers import RegisterSerializer, UserSerializer
from apps.audit.services import audit as audit_event
from apps.profiles.models import Profile
from apps.profiles.serializers import ProfileSerializer
from shared.exceptions import ValidationError


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            profile = Profile.objects.create(user=user, name="Default")
        audit_event(actor=user, action="user.registered", resource_type="user",
                    resource_id=user.pk, request=request)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "profile": ProfileSerializer(profile).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """Issues a fresh access/refresh token pair (§60)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            email = (request.data.get("email") or "").lower().strip()
            user = User.objects.filter(email=email).first()
            audit_event(actor=user, action="user.login", resource_type="user", request=request)
        return response


class LogoutView(APIView):
    """Blacklists the presented refresh token (§23 revocation strategy)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            raise ValidationError("Refresh token is required.")
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            raise ValidationError("Invalid refresh token.")
        audit_event(actor=request.user, action="user.logout", resource_type="user",
                    resource_id=request.user.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    """Initiate password reset: create token + dispatch email (§23)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        email = request.data.get("email")
        if not email:
            raise ValidationError("Email is required.")
        user = User.objects.filter(email=email).first()
        if user:
            from shared.crypto import generate_token
            from apps.accounts.services import PasswordResetTokenService

            token_service = PasswordResetTokenService(user)
            token_service.create_and_send()
        # Always return 200 without revealing whether address exists
        return Response({"detail": "If the address exists, a reset link has been sent."}, status=200)


class PasswordResetConfirmView(APIView):
    """Confirm password reset with token (§23)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        token_str = request.data.get("token")
        new_password = request.data.get("new_password")
        if not token_str or not new_password:
            raise ValidationError("Token and new password are required.")
        from apps.accounts.services import PasswordResetTokenService

        result = PasswordResetTokenService.confirm(token_str, new_password)
        if result["success"]:
            return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)
        raise ValidationError(result["error"])


class RefreshView(TokenRefreshView):
    """Token refresh with rotation+blacklist (config from SIMPLE_JWT)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    """Token refresh with rotation+blacklist (config from SIMPLE_JWT)."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
