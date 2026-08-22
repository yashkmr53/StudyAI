"""Celery tasks for audit/core operations (architecture §70)."""
import logging
import subprocess
import os
from datetime import datetime

from config.celery import app
from django.conf import settings

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=2, default_retry_delay=300)
def daily_backup(self):
    """Run pg_dump backup and invoke offsite copy hook (§70, gap A4/C2)."""
    from django.db import connection

    db = settings.DATABASES["default"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"/backups/{db['NAME']}_{stamp}.dump"

    os.makedirs("/backups", exist_ok=True)

    cmd = [
        "pg_dump",
        "-d", db["NAME"],
        "-f", out,
        "-Fc",
    ]
    if db.get("host"):
        cmd += ["-h", db["host"]]
    if db.get("port"):
        cmd += ["-p", str(db["port"])]
    if db.get("user"):
        cmd += ["-U", db["user"]]

    logger.info("Starting daily backup: %s", out)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("pg_dump failed: %s", exc)
        raise self.retry(exc=exc)

    size = os.path.getsize(out)
    logger.info("Backup written: %s (%s bytes)", out, size)

    # Invoke offsite copy hook (stub in Phase 10; replace in Phase 11)
    offsite_uri = os.environ.get("OFFSITE_BACKUP_URI")
    if offsite_uri:
        hook = "/app/scripts/backup_offsite_hook.sh"
        if os.path.exists(hook):
            logger.info("Invoking offsite hook: %s", hook)
            try:
                subprocess.run([hook, "--source-dir", "/backups", "--dest-uri", offsite_uri], check=True)
                logger.info("Offsite copy completed")
            except subprocess.CalledProcessError as exc:
                logger.error("Offsite hook failed: %s", exc)
                # Don't retry backup on offsite failure; log and alert instead
        else:
            logger.warning("Offsite hook not found at %s", hook)

    return {"file": out, "size": size}