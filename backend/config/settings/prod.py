import os
import sys

from .base import *  # noqa: F401,F403

DEBUG = os.environ.get("DJANGO_DEBUG", "0").strip() == "1"

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

_is_migration_command = any(
    cmd in sys.argv for cmd in [
        "migrate", "makemigrations", "showmigrations", "sqlmigrate",
        "dbshell", "createsuperuser", "inspectdb", "flush"
    ]
) or os.environ.get("DJANGO_DB_USER", "").lower() == "admin"

_app_user = os.environ.get("POSTGRES_APP_USER")
_app_password = os.environ.get("POSTGRES_APP_PASSWORD")

if _app_user and not _is_migration_command:
    db_user = _app_user
    db_password = _app_password if _app_password is not None else os.environ.get("POSTGRES_PASSWORD")
else:
    db_user = os.environ.get("POSTGRES_USER", "studyai")
    db_password = os.environ.get("POSTGRES_PASSWORD")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "studyai"),
        "USER": db_user,
        "PASSWORD": db_password,
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "OPTIONS": {"sslmode": os.environ.get("POSTGRES_SSLMODE", "require")},
    }
}


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip() == "1"


SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _flag("DJANGO_SECURE_SSL_REDIRECT", "1")
SESSION_COOKIE_SECURE = _flag("DJANGO_SESSION_COOKIE_SECURE", "1")
CSRF_COOKIE_SECURE = _flag("DJANGO_CSRF_COOKIE_SECURE", "1")
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

STATIC_ROOT = BASE_DIR / "var" / "static"

OBJECT_STORAGE_BACKEND = os.environ.get("OBJECT_STORAGE_BACKEND", "local")
OBJECT_STORAGE_LOCAL_DIR = os.environ.get(
    "OBJECT_STORAGE_LOCAL_DIR", str(BASE_DIR / "var" / "objectstore")
)
SIGNED_URL_TTL_SECONDS = int(os.environ.get("SIGNED_URL_TTL_SECONDS", "300"))
