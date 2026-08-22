import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class UserProfile(models.Model):
    """Per-user AI settings + budget (§21/§74, B8)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_profile"
    )
    # Daily budget (legacy — kept for backwards compat)
    daily_generation_limit = models.PositiveIntegerField(default=500)

    # Monthly token/cost budget (B8)
    monthly_token_budget = models.PositiveIntegerField(default=100000)
    monthly_cost_budget_usd = models.DecimalField(max_digits=10, decimal_places=2, default=50.00)
    current_month_token_usage = models.PositiveIntegerField(default=0)
    current_month_cost_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    budget_reset_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"AI Profile for {self.user.email}"
