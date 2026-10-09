"""Unit tests for database backup task and verification management command."""
import os
import tempfile
import time
from unittest import mock
from django.test import TestCase
from django.core.management import call_command

from apps.audit.tasks import _get_db_conn_info, _prune_old_backups, daily_backup


class DatabaseBackupTests(TestCase):
    def test_get_db_conn_info_structure(self):
        conn = _get_db_conn_info()
        self.assertIn("name", conn)
        self.assertIn("user", conn)
        self.assertIn("password", conn)
        self.assertIn("host", conn)
        self.assertIn("port", conn)
        self.assertTrue(conn["name"])
        self.assertTrue(conn["user"])

    def test_prune_old_backups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            now = time.time()
            old_file = os.path.join(tmpdir, "testdb_old.dump")
            new_file = os.path.join(tmpdir, "testdb_new.dump")
            other_file = os.path.join(tmpdir, "otherdb_old.dump")

            with open(old_file, "w") as f:
                f.write("dump")
            with open(new_file, "w") as f:
                f.write("dump")
            with open(other_file, "w") as f:
                f.write("dump")

            # Set mtime of old_file to 10 days ago
            ten_days_ago = now - (10 * 86400)
            os.utime(old_file, (ten_days_ago, ten_days_ago))
            os.utime(other_file, (ten_days_ago, ten_days_ago))

            pruned = _prune_old_backups(tmpdir, "testdb", retention_days=7)
            self.assertEqual(pruned, 1)
            self.assertFalse(os.path.exists(old_file))
            self.assertTrue(os.path.exists(new_file))
            self.assertTrue(os.path.exists(other_file))  # Ignored because db_name mismatch

    @mock.patch("subprocess.run")
    def test_daily_backup_execution(self, mock_subproc):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"BACKUP_DIR": tmpdir}):
                # Mock subprocess creating the backup file
                def side_effect(cmd, **kwargs):
                    out_path = cmd[cmd.index("-f") + 1]
                    with open(out_path, "wb") as f:
                        f.write(b"PGDUMP_CONTENT")
                    return mock.MagicMock(returncode=0)

                mock_subproc.side_effect = side_effect

                res = daily_backup(retention_days=7)
                self.assertIn("file", res)
                self.assertIn("size", res)
                self.assertTrue(os.path.exists(res["file"]))
                self.assertGreater(res["size"], 0)

                # Verify pg_dump was invoked with PGPASSWORD in env
                call_args, call_kwargs = mock_subproc.call_args
                cmd = call_args[0]
                self.assertEqual(cmd[0], "pg_dump")
                self.assertIn("-Fc", cmd)
                self.assertIn("env", call_kwargs)
                self.assertIn("PGPASSWORD", call_kwargs["env"])

    @mock.patch("subprocess.run")
    def test_verify_backup_command(self, mock_subproc):
        # Mock subprocess calls for verify_backup
        def side_effect(cmd, **kwargs):
            if "-c" in cmd and "SELECT 'documents'" in cmd[cmd.index("-c") + 1]:
                return mock.MagicMock(returncode=0, stdout="documents | 10\nusers | 5", stderr="")
            return mock.MagicMock(returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = side_effect

        with tempfile.NamedTemporaryFile(suffix=".dump") as tf:
            call_command("verify_backup", backup_file=tf.name, target_db="test_scratch_verify")
            self.assertTrue(mock_subproc.called)
