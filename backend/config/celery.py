import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("studyai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "reap-stuck-jobs": {
        "task": "apps.jobs.tasks.reap_stuck_jobs_task",
        "schedule": 300.0,  # every 5 minutes
    },
    "promote-retries": {
        "task": "apps.jobs.tasks.promote_retries_task",
        "schedule": 120.0,  # every 2 minutes
    },
    "daily-backup": {
        "task": "apps.audit.tasks.daily_backup",
        "schedule": crontab(hour=2, minute=30),  # 02:30 UTC daily
    },
    "reset-monthly-budgets": {
        "task": "apps.accounts.tasks.reset_monthly_budgets",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),  # 1st of month 00:00 UTC
    },
}
