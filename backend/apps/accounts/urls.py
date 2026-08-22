from django.urls import path
from apps.accounts.views import RefreshView

from apps.accounts import views

urlpatterns = [
    path("register", views.RegisterView.as_view(), name="auth-register"),
    path("login", views.LoginView.as_view(), name="auth-login"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("password-reset", views.PasswordResetView.as_view(), name="auth-password-reset"),
]
