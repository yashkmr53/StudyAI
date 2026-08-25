"""
Django settings for the StudyAI backend.

Values are environment-driven (12-factor). See .env.example at repo root.
"""
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = "django-insecure-dev-only-key-change-me"
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_prometheus",
    # Shared
    "shared",
    # Apps
    "apps.accounts",
    "apps.profiles",
    "apps.subjects",
    "apps.notebooks",
    "apps.canvas",
    "apps.documents",
    "apps.ingestion",
    "apps.notespace",
    "apps.ai_classroom",
    "apps.retrieval",
    "apps.questions",
    "apps.tests",
    "apps.chat",
    "apps.revision",
    "apps.references",
    "apps.jobs",
    "apps.evaluation",
    "apps.audit",
    "apps.agents",  # Phase 1: Agentic AI
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "shared.observability.request_id.RequestIDMiddleware",
    "shared.observability.metrics.SecurityHeadersMiddleware",
    "shared.observability.metrics.TimingMiddleware",
    "shared.database.middleware.RlsContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: PostgreSQL is the durable source of truth (architecture §2, §32).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "studyai",
        "USER": "yash",
        "HOST": "/tmp",
        "PORT": "5432",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "shared.exceptions.handlers.exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "auth": "30/min",
        "ai": "120/min",
        "user": "600/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "StudyAI API",
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Celery (architecture §2: Redis broker; PostgreSQL remains source of truth)
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False

# Object storage provider selection: "local" for v1 dev, s3 in production.
OBJECT_STORAGE_BACKEND = "local"
OBJECT_STORAGE_LOCAL_DIR = str(BASE_DIR / "var" / "objectstore")
SIGNED_URL_TTL_SECONDS = 300

# Canvas single-writer lock (architecture §5): expire ~90s without heartbeat.
CANVAS_LOCK_TTL_SECONDS = 90

# Ingestion / OCR (architecture §6, §28, §47)
OCR_PIPELINE_VERSION = "tesseract-v1"          # part of the OCR idempotency key (§20)
OCR_PROVIDER_CHAIN = "tesseract,mock"     # primary, fallback — comma-separated string
OCR_REVIEW_THRESHOLD = 0.80               # avg confidence below → needs_review (§48)
UPLOAD_MAX_BYTES = 10 * 1024 * 1024
UPLOAD_ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"]
# Must exceed UPLOAD_MAX_BYTES so bodies at the boundary reach our view,
# which returns a clean 413 envelope instead of Django's plain 400.
DATA_UPLOAD_MAX_MEMORY_SIZE = UPLOAD_MAX_BYTES + 64 * 1024

# Security hardening (§23)
UPLOAD_SNIFF_MAGIC_BYTES = True
RATE_LIMITING_ENABLED = True

# AI budget enforcement (§21/§74): max enrich+chat generations per profile/day.
AI_DAILY_BUDGET_PER_PROFILE = 500  # generous default; enforced when set

# NoteSpace PDF renderer (architecture §7, §49)
RENDERER_VERSION = "notespace-pdf-v1"

# AI Classroom retrieval foundation (architecture §8, §10, §14)
EMBEDDING_PROVIDER = "sentence_transformers"  # local embedder (MiniLM)
EMBEDDING_DIMENSIONS = 384
EMBEDDING_MODEL_VERSION = "sentence-transformers-all-MiniLM-L6-v2-v1"
CHUNKER_VERSION = "v1"
CHUNK_WORDS = 120                       # target chunk size in words (§10)
CHUNK_OVERLAP_WORDS = 30                # carried context window across chunk/page edges
RETRIEVAL_RRF_K = 60                    # Reciprocal Rank Fusion constant
RETRIEVAL_CANDIDATES = 50               # per-channel depth before fusion

# LLM Provider Chain (Phase 11)
LLM_PROVIDER_CHAIN = "ollama,mock"     # primary, fallback — comma-separated string

# Jobs runtime (architecture §19–20)
JOBS_MAX_ATTEMPTS = 3
JOBS_RETRY_BASE_SECONDS = 5
JOBS_RETRY_CAP_SECONDS = 300
JOBS_TIMEOUT_SECONDS = 600

# CORS / CSRF (§23)
CORS_ALLOWED_ORIGINS = []
CSRF_TRUSTED_ORIGINS = []

# Redis throttle cache (§23, D3)
REDIS_THROTTLE_URL = "redis://redis:6379/2"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
    "throttle": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_THROTTLE_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
}

# Prometheus metrics (§25, E)
PROMETHEUS_METRICS_ENABLED = False

# Enrichment coalescing window + change-magnitude threshold (§21, B7)
ENRICHMENT_COALESCE_WINDOW_SECONDS = 300
ENRICHMENT_CHANGE_MAGNITUDE_THRESHOLD = 0.15

# Provider input limits (D5 data-minimization)
MAX_PROVIDER_INPUT_CHARS = 8000

# Monthly AI budget defaults (B8) — per-user overrides via admin
DEFAULT_MONTHLY_TOKEN_BUDGET = 100000
DEFAULT_MONTHLY_COST_BUDGET_USD = 50.00

# Phase 1: Agentic AI Settings
AGENT_ENABLED = True
AGENT_MAX_ITERATIONS = 5
AGENT_MAX_TOOL_CALLS = 10
AGENT_REQUEST_TIMEOUT_SECONDS = 60
AGENT_PER_TOOL_TIMEOUT_SECONDS = 30
AGENT_PROMPT_VERSION = "agent_orchestrator:v1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "{levelname} {asctime} {name} request_id={request_id} {message}",
            "style": "{",
        },
    },
    "filters": {
        "request_id": {"()": "shared.observability.request_id.RequestIDLogFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "fontTools": {"level": "WARNING"},
    },
}
