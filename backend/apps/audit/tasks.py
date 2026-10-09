"""Celery tasks for audit/core operations (architecture §70)."""
import glob
import logging
import os
import subprocess
from datetime import datetime, timedelta

from config.celery import app
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_db_conn_info():
    db = settings.DATABASES.get("default", {})
    return {
        "name": os.environ.get("POSTGRES_DB") or db.get("NAME") or "studyai",
        "user": os.environ.get("POSTGRES_USER") or db.get("USER") or db.get("user") or "studyai",
        "password": os.environ.get("POSTGRES_PASSWORD") or db.get("PASSWORD") or db.get("password") or "",
        "host": os.environ.get("POSTGRES_HOST") or db.get("HOST") or db.get("host") or "localhost",
        "port": str(os.environ.get("POSTGRES_PORT") or db.get("PORT") or db.get("port") or "5432"),
    }


def _prune_old_backups(backup_dir: str, db_name: str, retention_days: int = 7) -> int:
    """Delete backups older than retention_days."""
    pattern = os.path.join(backup_dir, f"{db_name}_*.dump")
    cutoff = datetime.now() - timedelta(days=retention_days)
    pruned = 0
    for file_path in glob.glob(pattern):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            if mtime < cutoff:
                os.remove(file_path)
                pruned += 1
                logger.info("Pruned old backup: %s (mtime=%s)", file_path, mtime)
        except Exception as err:
            logger.warning("Error pruning backup %s: %s", file_path, err)
    return pruned


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def daily_backup(self, retention_days: int = 7):
    """Run pg_dump backup, enforce retention, and invoke offsite copy hook (§70)."""
    conn = _get_db_conn_info()
    backup_dir = os.environ.get("BACKUP_DIR", "/backups")
    os.makedirs(backup_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(backup_dir, f"{conn['name']}_{stamp}.dump")

    cmd = [
        "pg_dump",
        "-d", conn["name"],
        "-f", out,
        "-Fc",
        "-h", conn["host"],
        "-p", conn["port"],
        "-U", conn["user"],
    ]

    env = os.environ.copy()
    if conn["password"]:
        env["PGPASSWORD"] = str(conn["password"])

    logger.info(
        "Starting database backup: target=%s, db=%s, host=%s, user=%s",
        out, conn["name"], conn["host"], conn["user"]
    )
    try:
        subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        # Never log database password
        logger.error("Database backup failed: returncode=%s, stderr=%s", exc.returncode, exc.stderr)
        raise self.retry(exc=exc)
    except FileNotFoundError as exc:
        logger.error("pg_dump executable not found: %s", exc)
        raise exc

    if not os.path.exists(out) or os.path.getsize(out) == 0:
        logger.error("Backup file was not created or is empty: %s", out)
        raise RuntimeError(f"Backup file empty or missing: {out}")

    size = os.path.getsize(out)
    logger.info("Backup successfully written: %s (%s bytes)", out, size)

    # Prune old backups exceeding retention days
    _prune_old_backups(backup_dir, conn["name"], retention_days=retention_days)

    # Invoke offsite copy hook if configured
    offsite_uri = os.environ.get("OFFSITE_BACKUP_URI")
    if offsite_uri:
        hook = "/app/scripts/backup_offsite_hook.sh"
        if os.path.exists(hook):
            logger.info("Invoking offsite hook: %s -> %s", hook, offsite_uri)
            try:
                subprocess.run([hook, "--source-dir", backup_dir, "--dest-uri", offsite_uri], check=True)
                logger.info("Offsite copy completed")
            except subprocess.CalledProcessError as exc:
                logger.error("Offsite hook failed: %s", exc)
        else:
            logger.warning("Offsite hook script not found at %s", hook)

    return {"file": out, "size": size, "db": conn["name"], "timestamp": stamp}