"""CI settings: PostgreSQL service container, no socket auth."""
import os

from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "studyai_test"),
        "USER": os.environ.get("POSTGRES_USER", "studyai"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True

RATE_LIMITING_ENABLED = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
    },
    "throttle": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache"
    },
}

STORAGE_BACKEND = "local"
OBJECT_STORAGE_BACKEND = "local"

WEB_SEARCH_PROVIDER = "mock"

LANGSMITH_TRACING = False
