from rest_framework.test import APIClient


def authenticated_client(email: str, password: str) -> APIClient:
    """Register/login through the real API and attach the bearer token."""
    from apps.accounts.models import User

    if not User.objects.filter(email=email).exists():
        response = APIClient().post(
            "/api/v1/auth/register",
            {"email": email, "password": password},
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
    return client
