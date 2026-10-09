"""Database backup/restore + verification (architecture §70).

Real pg_dump/pg_restore drills against the configured database. The
restore command refuses to run against the live database name unless
--force is passed twice.
"""
import os
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _db_settings():
    db = settings.DATABASES.get("default", {})
    return {
        "name": os.environ.get("POSTGRES_DB") or db.get("NAME") or "studyai",
        "user": os.environ.get("POSTGRES_USER") or db.get("USER") or db.get("user") or "studyai",
        "password": os.environ.get("POSTGRES_PASSWORD") or db.get("PASSWORD") or db.get("password") or "",
        "host": os.environ.get("POSTGRES_HOST") or db.get("HOST") or db.get("host") or "localhost",
        "port": str(os.environ.get("POSTGRES_PORT") or db.get("PORT") or db.get("port") or "5432"),
    }


class Command(BaseCommand):
    help = "Backup the database with pg_dump into a timestamped file."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="backups")
        parser.add_argument("--format", default="plain", choices=["plain", "custom"])

    def handle(self, *args, **options):
        from datetime import datetime

        db = _db_settings()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = ".dump" if options["format"] == "custom" else ".sql"
        out = f"{options['output_dir']}/{db['name']}_{stamp}{suffix}"

        os.makedirs(options["output_dir"], exist_ok=True)

        cmd = ["pg_dump", "-d", db["name"], "-f", out]
        if options["format"] == "custom":
            cmd += ["-Fc"]
        if db["host"]:
            cmd += ["-h", db["host"]]
        if db["port"]:
            cmd += ["-p", db["port"]]
        if db["user"]:
            cmd += ["-U", db["user"]]

        env = os.environ.copy()
        if db["password"]:
            env["PGPASSWORD"] = str(db["password"])

        self.stdout.write(f"Running pg_dump for database {db['name']} on {db['host']}:{db['port']}...")
        subprocess.run(cmd, env=env, check=True)
        size = os.path.getsize(out)
        self.stdout.write(self.style.SUCCESS(f"Backup written: {out} ({size} bytes)"))
