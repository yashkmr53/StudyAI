"""Phase 13: Password Reset Reliability & Security Tests.

Verifies:
1. Complete password reset initiation and confirmation flow.
2. User login with new password and rejection of old password.
3. Unknown email enumeration protection (returns identical 200 response).
4. Invalid token rejection.
5. Expired token rejection.
6. Replay attack rejection (used token cannot be reused).
7. Concurrent redemption protection (single-use guarantee).
8. Weak password rejection (< 10 chars).
9. Token cleanup (invalidation of previous tokens).
"""

import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import PasswordResetToken, User
from apps.accounts.services.password_reset import PasswordResetTokenService


class PasswordResetAPITests(TestCase):
    def setUp(self):
        self.email = "student_reset@example.com"
        self.old_password = "initialSecurePass1!"
        self.new_password = "updatedSecurePass2@"
        self.user = User.objects.create_user(email=self.email, password=self.old_password)

    def test_successful_password_reset_flow(self):
        """User requests reset, receives token, confirms reset, and logs in with new password."""
        # 1. Initiate password reset
        resp = self.client.post(
            "/api/v1/auth/password-reset",
            {"email": self.email},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json()["detail"],
            "If the address exists, a reset link has been sent.",
        )

        # 2. Check token in DB
        token_record = PasswordResetToken.objects.filter(user=self.user, used=False).first()
        self.assertIsNotNone(token_record)
        self.assertFalse(token_record.used)
        self.assertGreater(token_record.expires_at, timezone.now())

        # Generate a raw token through service to test confirm endpoint
        svc_result = PasswordResetTokenService(self.user).create_and_send()
        raw_token = svc_result["raw_token"]

        # Verify DB stores hash, NOT raw token
        db_token = PasswordResetToken.objects.get(id=svc_result["token_id"])
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.assertEqual(db_token.token, expected_hash)
        self.assertNotEqual(db_token.token, raw_token)

        # 3. Confirm password reset
        confirm_resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw_token, "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertEqual(confirm_resp.json()["detail"], "Password reset successful.")

        # 4. Token marked as used
        db_token.refresh_from_db()
        self.assertTrue(db_token.used)

        # 5. Verify user can log in with new password
        login_new = self.client.post(
            "/api/v1/auth/login",
            {"email": self.email, "password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(login_new.status_code, 200)
        self.assertIn("access", login_new.json())

        # 6. Verify user CANNOT log in with old password
        login_old = self.client.post(
            "/api/v1/auth/login",
            {"email": self.email, "password": self.old_password},
            content_type="application/json",
        )
        self.assertEqual(login_old.status_code, 401)

    def test_unknown_email_enumeration_protection(self):
        """Unknown email returns 200 identical response without creating token."""
        resp = self.client.post(
            "/api/v1/auth/password-reset",
            {"email": "nonexistent_user@example.com"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json()["detail"],
            "If the address exists, a reset link has been sent.",
        )
        self.assertEqual(
            PasswordResetToken.objects.filter(user__email="nonexistent_user@example.com").count(),
            0,
        )

    def test_missing_email_rejected_with_422(self):
        """Missing email returns validation error."""
        resp = self.client.post(
            "/api/v1/auth/password-reset",
            {"email": ""},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_invalid_token_rejected(self):
        """Bogus token is rejected."""
        resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": "completely_invalid_token_string", "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_expired_token_rejected(self):
        """Expired token cannot be used."""
        svc_result = PasswordResetTokenService(self.user).create_and_send()
        raw_token = svc_result["raw_token"]

        # Backdate expiration
        PasswordResetToken.objects.filter(id=svc_result["token_id"]).update(
            expires_at=timezone.now() - timedelta(minutes=10)
        )

        resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw_token, "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_token_replay_rejected(self):
        """Used token cannot be reused (replay protection)."""
        svc_result = PasswordResetTokenService(self.user).create_and_send()
        raw_token = svc_result["raw_token"]

        # First reset succeeds
        first_resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw_token, "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(first_resp.status_code, 200)

        # Second reset with same token fails
        second_resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw_token, "new_password": "thirdSecurePass3#"},
            content_type="application/json",
        )
        self.assertEqual(second_resp.status_code, 422)

    def test_short_password_rejected(self):
        """Password shorter than 10 characters is rejected."""
        svc_result = PasswordResetTokenService(self.user).create_and_send()
        raw_token = svc_result["raw_token"]

        resp = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw_token, "new_password": "short"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_new_request_invalidates_previous_unused_token(self):
        """Requesting a new reset token invalidates any existing unused tokens."""
        res1 = PasswordResetTokenService(self.user).create_and_send()
        raw1 = res1["raw_token"]

        # Request second token
        res2 = PasswordResetTokenService(self.user).create_and_send()
        raw2 = res2["raw_token"]

        # First token should now be gone/invalid
        confirm1 = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw1, "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(confirm1.status_code, 422)

        # Second token succeeds
        confirm2 = self.client.post(
            "/api/v1/auth/password-reset-confirm",
            {"token": raw2, "new_password": self.new_password},
            content_type="application/json",
        )
        self.assertEqual(confirm2.status_code, 200)

    def test_concurrent_redemption_protection(self):
        """Simultaneous/sequential redemptions cannot both succeed (single-use guarantee)."""
        import concurrent.futures
        from django.db import connection

        svc_result = PasswordResetTokenService(self.user).create_and_send()
        raw_token = svc_result["raw_token"]

        if connection.vendor == "sqlite":
            # SQLite in-memory test DB cannot share memory across threads without URI mode
            res1 = PasswordResetTokenService.confirm(raw_token, "ConcPass1111!")
            res2 = PasswordResetTokenService.confirm(raw_token, "ConcPass2222!")
            self.assertTrue(res1.get("success"))
            self.assertFalse(res2.get("success"))
            self.assertIn("already been used", res2.get("error"))
        else:
            results = []

            def attempt_redeem(pwd):
                connection.close()
                res = PasswordResetTokenService.confirm(raw_token, pwd)
                results.append(res)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(attempt_redeem, "ConcPass1111!")
                f2 = executor.submit(attempt_redeem, "ConcPass2222!")
                concurrent.futures.wait([f1, f2])

            successes = [r for r in results if r.get("success")]
            failures = [r for r in results if not r.get("success")]
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            self.assertIn("already been used", failures[0]["error"])
