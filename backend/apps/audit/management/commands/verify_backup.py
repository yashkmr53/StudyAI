"""Restore drill: verify a backup by restoring it into a scratch database
and running a row-count smoke query (architecture §70 recovery test).

Refuses to touch the live database — the target must be a *_restore db.
"""
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify a backup: restore into a scratch database and run a smoke query."

    def add_arguments(self, parser):
        parser.add_argument("--backup-file", required=True)
        parser.add_argument("--target-db", default=None, help="Scratch DB name (default: <db>_restore_verify)")

    def handle(self, *args, **options):
        from django.db import connection

        live = settings.DATABASES["default"]["NAME"]
        target = options["target_db"] or f"{live}_restore_verify"
        if target == live:
            raise CommandError("Refusing to restore over the live database.")

        backup_file = options["backup_file"]
        is_custom = backup_file.endswith(".dump")

        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS "{target}";')
            cursor.execute(f'CREATE DATABASE "{target}";')

        restore_cmd = ["pg_restore", "-d", target, "--no-owner"] if is_custom else [
            "psql", "-d", target, "-q", "-f", backup_file
        ]
        self.stdout.write(f"Restoring {backup_file} into {target}…")
        subprocess.run(restore_cmd, check=True)

        # smoke query: count rows in a core table if present
        check_sql = (
            "SELECT 'documents', count(*) FROM documents_document "
            "UNION ALL SELECT 'users', count(*) FROM accounts_user;"
        )
        out = subprocess.run(
            ["psql", "-d", target, "-t", "-c", check_sql],
            capture_output=True, text=True,
        )
        self.stdout.write(out.stdout or "(no output)")
        if out.returncode != 0:
            raise CommandError(out.stderr)
        self.stdout.write(self.style.SUCCESS(f"Restore verified into {target}. Drop it when done."))
