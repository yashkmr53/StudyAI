from django.urls import path

from apps.accounts.views import (
    RegisterView,
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordResetConfirmView,
    RefreshView,
)

urlpatterns = [
    path("register", RegisterView.as_view(), name="auth-register"),
    path("login", LoginView.as_view(), name="auth-login"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("password-reset", PasswordResetView.as_view(), name="auth-password-reset"),
    path("password-reset-confirm", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
]
