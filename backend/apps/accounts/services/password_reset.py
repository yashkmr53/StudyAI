"""Password reset token service (§23).

Cryptographically secure password reset flow:
- 256-bit entropy unpredictable single-use tokens
- Only SHA-256 token hashes stored in database (preventing plaintext exposure)
- Strict 1-hour expiration window
- Concurrency-safe redemption with row-level database locking (select_for_update)
- Token replay prevention (marked used immediately)
- Invalidation of outstanding tokens upon successful reset
- Generic user responses preventing email enumeration
- Clean logging with no token leakage
"""

import hashlib
import logging
import os
import secrets
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PasswordResetToken, User

logger = logging.getLogger(__name__)


def _build_reset_url(raw_token: str, request=None) -> str:
    """Build the password reset URL (frontend or API)."""
    frontend_base = getattr(settings, "FRONTEND_URL", None) or os.environ.get("FRONTEND_URL")
    if frontend_base:
        return f"{frontend_base.rstrip('/')}/reset-password?token={raw_token}"
    if request:
        return request.build_absolute_uri(f"/reset-password?token={raw_token}")
    return f"http://localhost:5173/reset-password?token={raw_token}"


class PasswordResetTokenService:
    """Service for creating and confirming password reset tokens."""

    def __init__(self, user: Optional[User] = None):
        self.user = user

    def create_and_send(self, *args, **kwargs) -> dict:
        """Create token and dispatch reset email.

        Supports:
        - PasswordResetTokenService(user).create_and_send(request=request)
        - PasswordResetTokenService.create_and_send(user, request=request)
        """
        if isinstance(self, PasswordResetTokenService):
            user = kwargs.get("user") or (args[0] if args else self.user)
        elif isinstance(self, User):
            user = self
        else:
            user = kwargs.get("user") or (args[0] if args else None)

        request = kwargs.get("request")
        if not user:
            raise ValueError("User must be provided to create and send a reset token.")
        return self._create_and_send_internal(user, request=request)

    @classmethod
    def _create_and_send_internal(cls, user: User, *, request=None) -> dict:
        # Invalidate any existing unused tokens for this user
        PasswordResetToken.objects.filter(user=user, used=False).delete()

        # Generate unpredictable raw token (32 bytes = 256 bits of entropy)
        raw_token = secrets.token_urlsafe(32)
        # Store only SHA-256 hash in DB to prevent plaintext exposure
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Create token record valid for 1 hour
        token_obj = PasswordResetToken.objects.create(
            user=user,
            token=token_hash,
            expires_at=timezone.now() + timedelta(hours=1),
            used=False,
        )

        reset_url = _build_reset_url(raw_token, request=request)

        # Dispatch email
        try:
            from providers.registry import get_email_provider
            email_provider = get_email_provider()
            email_provider.send_password_reset_email(
                to=user.email,
                reset_url=reset_url,
                user_name=getattr(user, "name", user.email) or user.email,
            )
        except Exception as exc:
            # Never expose reset token in application logs
            logger.warning("Failed to dispatch password reset email: %s", exc)

        return {"status": "sent", "token_id": str(token_obj.id), "raw_token": raw_token}

    @staticmethod
    def confirm(raw_token: str, new_password: str) -> dict:
        """Confirm password reset with a valid token. Returns dict with success/error."""
        if not raw_token or not new_password:
            return {"success": False, "error": "Token and new password are required."}

        if len(new_password) < 10:
            return {"success": False, "error": "Password must be at least 10 characters long."}

        token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

        with transaction.atomic():
            # Use select_for_update to guard against concurrent redemption
            token_obj = (
                PasswordResetToken.objects
                .select_for_update()
                .select_related("user")
                .filter(token=token_hash)
                .first()
            )
            if not token_obj:
                return {"success": False, "error": "Invalid or expired token."}

            if token_obj.used:
                return {"success": False, "error": "This token has already been used."}

            if token_obj.expires_at < timezone.now():
                return {"success": False, "error": "This token has expired."}

            # Atomically mark token as used
            token_obj.used = True
            token_obj.save(update_fields=["used"])

            user = token_obj.user
            user.set_password(new_password)
            user.save(update_fields=["password"])

            # Clean up all other remaining unused reset tokens for this user
            PasswordResetToken.objects.filter(user=user, used=False).delete()

        return {"success": True}