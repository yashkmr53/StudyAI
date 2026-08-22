from django.test import TestCase


class AuthFlowAPITests(TestCase):
    def register(self, email="student@example.com", password="s3curePass!x"):
        return self.client.post(
            "/api/v1/auth/register",
            {"email": email, "password": password},
            content_type="application/json",
        )

    def test_register_creates_user_profile_and_tokens(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body["profile"]["name"], "Default")
        self.assertEqual(body["user"]["email"], "student@example.com")

    def test_register_rejects_short_password_with_error_envelope(self):
        response = self.register(password="short")
        self.assertEqual(response.status_code, 422)
        error = response.json()["error"]
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertTrue(error["request_id"].startswith("req_"))
        self.assertIn("password", error["details"])

    def test_register_is_idempotent_per_email(self):
        self.assertEqual(self.register().status_code, 201)
        response = self.register()
        self.assertEqual(response.status_code, 422)

    def test_login_returns_tokens(self):
        self.register()
        response = self.client.post(
            "/api/v1/auth/login",
            {"email": "student@example.com", "password": "s3curePass!x"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_logout_blacklists_refresh_token(self):
        tokens = self.register().json()
        response = self.client.post(
            "/api/v1/auth/logout",
            {"refresh": tokens["refresh"]},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
        )
        self.assertEqual(response.status_code, 204)
        refresh_response = self.client.post(
            "/api/v1/auth/refresh",
            {"refresh": tokens["refresh"]},
            content_type="application/json",
        )
        self.assertEqual(refresh_response.status_code, 401)

    def test_unauthenticated_request_uses_envelope(self):
        response = self.client.get("/api/v1/profiles")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
