"""Password reset token service (§23)."""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone as tz_module

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.accounts.models import User, PasswordResetToken


def _build_reset_url(token: str, request=None) -> str:
    """Build the absolute password reset URL."""
    from django.urls import reverse
    base = request.build_absolute_uri(reverse("auth-password-reset-confirm")) if request else f"https://example.com/reset/{token}"
    return f"{base}?token={token}"


class PasswordResetTokenService:
    """Service for creating and confirming password reset tokens."""

    @staticmethod
    def create_and_send(user: User, *, request=None) -> dict:
        """Create a token and send reset email. Returns dict with status."""
        from shared.exceptions import ImproperlyConfigured

        # Delete any existing unused tokens for this user
        PasswordResetToken.objects.filter(user=user, used=False).delete()

        # Create a new token
        token_obj = PasswordResetToken.objects.create(
            user=user,
            token=PasswordResetTokenService._generate_token(user),
            expires_at=datetime.now(tz_module.utc) + timedelta(hours=1),
        )

        # Build reset URL
        reset_url = _build_reset_url(token_obj.token, request=request)

        # Send email
        try:
            email_from = getattr(settings, "EMAIL_FROM", "noreply@studyai.local")
            subject = "Reset your StudyAI password"
            text_body = f"""
Hi {user.email},

You requested a password reset. Click the link below to set a new password:

{reset_url}

This link expires in 1 hour. If you didn't request this, please ignore this email.

-- The StudyAI Team
"""
            html_body = f"""
<h1>Reset your StudyAI password</h1>
<p>Hi {user.email},</p>
<p>You requested a password reset. Click the link below to set a new password:</p>
<p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 4px;">Reset Password</a></p>
<p>This link expires in 1 hour. If you didn't request this, please ignore this email.</p>
<p>-- The StudyAI Team</p>
"""

            # Use the email provider from registry
            from providers.registry import get_email_provider
            email_provider = get_email_provider()
            email_provider.send_password_reset_email(
                to=user.email,
                reset_url=reset_url,
                user_name=user.email,
            )
        except Exception as e:
            # Log but don't fail the token creation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Failed to send password reset email: %s", e)

        return {"status": "sent", "token": token_obj.token}

    @staticmethod
    def _generate_token(user: User) -> str:
        """Generate a unique token for the user."""
        salt = settings.SECRET_KEY[:16]
        data = f"{user.pk}:{secrets.token_urlsafe(32)}"
        return hashlib.sha256((salt + data).encode()).hexdigest()[:64]

    @staticmethod
    def confirm(token_str: str, new_password: str) -> dict:
        """Confirm password reset with a valid token. Returns dict with success/error."""
        try:
            signer = signing.TimestampSigner()
            payload = signer.unsign_object(token_str, max_age=3600)
        except signing.BadSignature:
            return {"success": False, "error": "Invalid or expired token."}
        except signing.SignatureExpired:
            return {"success": False, "error": "Invalid or expired token."}

        user_id = payload.get("user_id")
        if not user_id:
            return {"success": False, "error": "Invalid token payload."}

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return {"success": False, "error": "User not found."}

        # Mark token as used and reset password
        PasswordResetToken.objects.filter(pk=payload.get("token_id")).update(used=True)

        user.set_password(new_password)
        user.save(update_fields=("password",))

        # Force password update by clearing JWT etc.
        # The user will need to login fresh

        return {"success": True, "error": None}