import os

# The worker container inherits DJANGO_SETTINGS_MODULE=config.settings.prod
# from docker-compose, which overrides pytest.ini. Force test-critical
# overrides so tests execute correctly without requiring
# --ds=config.settings.test on every invocation.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

try:
    import django.conf
    django.conf.settings.CELERY_TASK_ALWAYS_EAGER = True
except Exception:
    pass
