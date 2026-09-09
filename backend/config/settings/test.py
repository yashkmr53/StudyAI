from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"

REST_FRAMEWORK = {**REST_FRAMEWORK}  # noqa: F405
REST_FRAMEWORK["TEST_REQUEST_DEFAULT_FORMAT"] = "json"

LOGGING["loggers"] = {
    "django.db.backends": {"level": "DEBUG", "handlers": ["console"]},
}

# verbose SQL off; keep throttle debug

# Throttling must not leak counters across tests: disable cache by default.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}

RATE_LIMITING_ENABLED = False  # enabled per-test via override_settings

# Use mock providers for deterministic tests
LLM_PROVIDER_CHAIN = "mock,mock"
WEB_SEARCH_PROVIDER = "mock"
OCR_PROVIDER_CHAIN = "mock,mock"
EMAIL_BACKEND = "console"

# Use hashing embedder for tests (no ML dependencies)
EMBEDDING_PROVIDER = "hashing"
EMBEDDING_MODEL_VERSION = "hashing-384-v1"

# Disable LangSmith tracing during tests to avoid rate limits
LANGSMITH_TRACING = False
