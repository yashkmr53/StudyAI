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
    help = "Verify a backup: restore into a scratch database and run a smoke query."

    def add_arguments(self, parser):
        parser.add_argument("--backup-file", required=True)
        parser.add_argument("--target-db", default=None, help="Scratch DB name (default: <db>_restore_verify)")

    def handle(self, *args, **options):
        from django.db import connection

        db = _db_settings()
        live = db["name"]
        target = options["target_db"] or f"{live}_restore_verify"
        if target == live:
            raise CommandError("Refusing to restore over the live database.")

        backup_file = options["backup_file"]
        is_custom = backup_file.endswith(".dump")

        env = os.environ.copy()
        if db["password"]:
            env["PGPASSWORD"] = str(db["password"])

        admin_base = ["psql", "-h", db["host"], "-p", db["port"], "-U", db["user"], "-d", "studyai"]
        subprocess.run(admin_base + ["-c", f'DROP DATABASE IF EXISTS "{target}";'], env=env, check=True)
        subprocess.run(admin_base + ["-c", f'CREATE DATABASE "{target}";'], env=env, check=True)

        restore_cmd = [
            "pg_restore",
            "-d", target,
            "-h", db["host"],
            "-p", db["port"],
            "-U", db["user"],
            "--no-owner",
            backup_file,
        ] if is_custom else [
            "psql",
            "-d", target,
            "-h", db["host"],
            "-p", db["port"],
            "-U", db["user"],
            "-q",
            "-f", backup_file,
        ]
        self.stdout.write(f"Restoring {backup_file} into {target} on {db['host']}:{db['port']}...")
        res = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)
        if res.returncode == 0:
            self.stdout.write("Restore command executed cleanly.")
        elif res.returncode == 1 and is_custom:
            self.stdout.write(self.style.WARNING(f"pg_restore finished with non-fatal warnings: {res.stderr.strip()}"))
        else:
            raise CommandError(f"Restore command failed (exit code {res.returncode}): {res.stderr}")

        # smoke query: count rows in core tables
        check_sql = (
            "SELECT 'documents', count(*) FROM documents_document "
            "UNION ALL SELECT 'users', count(*) FROM accounts_user;"
        )
        check_cmd = [
            "psql",
            "-d", target,
            "-h", db["host"],
            "-p", db["port"],
            "-U", db["user"],
            "-t",
            "-c", check_sql,
        ]
        out = subprocess.run(check_cmd, env=env, capture_output=True, text=True)
        self.stdout.write(out.stdout or "(no output)")
        if out.returncode != 0:
            raise CommandError(out.stderr)

        # Clean up scratch database after verification
        subprocess.run(admin_base + ["-c", f'DROP DATABASE IF EXISTS "{target}";'], env=env, check=True)
        self.stdout.write(self.style.SUCCESS(f"Restore verified into {target} and scratch database cleaned up."))
