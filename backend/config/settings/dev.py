import os

from .base import *  # noqa: F401,F403

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

# Local dev has no Redis: run jobs inline after the request commits.
# Production must keep this False and run Celery workers (or process_jobs).
CELERY_TASK_ALWAYS_EAGER = True

RATE_LIMITING_ENABLED = False  # local dev: avoid cross-test throttle state
