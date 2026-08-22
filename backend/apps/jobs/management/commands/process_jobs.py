"""DB-polling job executor (architecture §24 alternative).

Runs the same durable Job state machine without Redis/Celery:
promote due retries → claim → execute. Use `--loop` for a long-running
worker process; default is a single pass (cron-friendly).
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Process queued jobs via DB polling (no broker required)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Run continuously.")
        parser.add_argument("--interval", type=float, default=2.0, help="Seconds between polls in --loop mode.")
        parser.add_argument("--reap", action="store_true", help="Also reap stuck RUNNING jobs each pass.")

    def handle(self, *args, **options):
        from apps.jobs.models import Job
        from apps.jobs.services import promote_due_retries, reap_stuck_jobs, run_claimed_job

        while True:
            if options["reap"]:
                reaped = reap_stuck_jobs(timezone.now())
                if reaped:
                    self.stdout.write(f"Reaped {reaped} stuck jobs")
            promote_due_retries(timezone.now())
            candidates = list(
                Job.objects.filter(status=Job.Status.QUEUED).order_by("created_at").values_list("pk", flat=True)[:50]
            )
            processed = 0
            for pk in candidates:
                job = Job.objects.get(pk=pk)
                if job.claim():
                    run_claimed_job(job)
                    processed += 1
            if not options["loop"]:
                self.stdout.write(f"Processed {processed} job(s).")
                return
            import time

            time.sleep(options["interval"])
