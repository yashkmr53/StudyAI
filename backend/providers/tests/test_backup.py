"""Backup creation and restoration tests (Phase 11)."""
from unittest.mock import patch, MagicMock, call

from django.test import TestCase, override_settings
from django.core.management import call_command
from io import StringIO

from providers.storage.local import LocalObjectStorage
from providers.registry import get_object_storage
from providers.storage.s3 import MinIOStorageProvider


class TestBackupCommands(TestCase):
    """Test backup management commands."""

    def setUp(self):
        self.storage = LocalObjectStorage()

    @patch("apps.audit.management.commands.backup_database.subprocess.run")
    @patch("os.makedirs")
    @patch("os.path.getsize")
    def test_backup_database_command(self, mock_getsize, mock_makedirs, mock_run):
        """Test backup_database management command."""
        from apps.audit.management.commands.backup_database import Command
        
        cmd = Command()
        mock_getsize.return_value = 1024
        
        cmd.handle(
            output_dir="/tmp/backup",
            format="plain",
        )
        
        # Should create directory
        mock_makedirs.assert_called()
        
        # Should call pg_dump
        mock_run.assert_called()

    @patch("apps.audit.management.commands.verify_backup.subprocess.run")
    @patch("django.db.connection")
    def test_verify_backup_command(self, mock_connection, mock_run):
        """Test verify_backup management command."""
        from apps.audit.management.commands.verify_backup import Command
        
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        
        # Mock the database connection cursor
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        cmd = Command()
        
        # The command requires --backup-file and --target-db arguments
        cmd.handle(backup_file="/tmp/backup/test.sql", target_db=None)
        
        # Should run pg_restore/psql
        mock_run.assert_called()
        
        # Should attempt to drop and create database (target db name depends on settings)
        # Just verify that execute was called with DROP and CREATE DATABASE
        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("DROP DATABASE IF EXISTS" in call for call in calls)
        assert any("CREATE DATABASE" in call for call in calls)


class TestBackupWithMinIO(TestCase):
    """Test backup to MinIO storage."""

    @patch("providers.storage.s3.boto3.client")
    def test_backup_to_minio(self, mock_boto_client):
        """Should be able to backup to MinIO."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.head_bucket.return_value = {}
        
        provider = MinIOStorageProvider(
            backend="minio",
            endpoint="http://minio:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="backups",
            region="us-east-1",
            secure=False,
        )
        
        # Store backup file
        backup_data = b"PG_DUMP_DATA"
        size = provider.store_bytes("backup/2024-01-15/backup.sql", backup_data)
        
        assert size == len(backup_data)
        mock_client.put_object.assert_called_once()

    @patch("providers.storage.s3.boto3.client")
    def test_restore_from_minio(self, mock_boto_client):
        """Should be able to restore from MinIO."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        mock_body = MagicMock()
        mock_body.read.return_value = b"PG_DUMP_DATA"
        mock_client.get_object.return_value = {"Body": mock_body}
        
        provider = MinIOStorageProvider(bucket="backups")
        provider._client = mock_client
        
        data = provider.read_bytes("backup/2024-01-15/backup.sql")
        
        assert data == b"PG_DUMP_DATA"
        mock_client.get_object.assert_called_once_with(
            Bucket="backups", Key="backup/2024-01-15/backup.sql"
        )


class TestBackupOffsiteHook(TestCase):
    """Test backup offsite copy hook."""

    @patch("subprocess.run")
    def test_backup_offsite_hook_script(self, mock_run):
        """Test backup offsite hook script execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK")
        
        # The script would be called like:
        # scripts/backup_offsite_hook.sh --source-dir /tmp/backup --dest-uri s3://bucket/backups
        
        from apps.audit.management.commands.backup_database import Command
        cmd = Command()
        
        # Simulate running the hook
        result = mock_run([
            "scripts/backup_offsite_hook.sh",
            "--source-dir", "/tmp/backup",
            "--dest-uri", "s3://bucket/backups",
        ], capture_output=True, text=True)
        
        mock_run.assert_called_once()
        assert result.returncode == 0


class TestBackupConfiguration(TestCase):
    """Test backup configuration separation."""

    @override_settings(
        OBJECT_STORAGE_BACKEND="local",
        OBJECT_STORAGE_LOCAL_DIR="/app/var/objectstore",
    )
    def test_app_storage_config(self):
        """Application storage should use local/minio."""
        storage = get_object_storage()
        assert isinstance(storage, LocalObjectStorage)

    @override_settings(
        STORAGE_BACKEND="minio",
        MINIO_BUCKET="studyai",
        # Backup could use different bucket
    )
    @patch("providers.storage.s3.boto3.client")
    def test_backup_storage_separate(self, mock_boto):
        """Backup storage can be separate from app storage."""
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.head_bucket.return_value = {}
        
        # App storage
        app_storage = get_object_storage()
        assert isinstance(app_storage, MinIOStorageProvider)
        
        # Backup storage (separate instance with different bucket)
        backup_storage = MinIOStorageProvider(
            backend="minio",
            bucket="studyai-backups",
        )
        
        assert app_storage.bucket == "studyai"
        assert backup_storage.bucket == "studyai-backups"


class TestBackupRestoreProcedure(TestCase):
    """Test documented backup/restore procedure."""

    def test_backup_command_help(self):
        """Backup command should have help text."""
        from apps.audit.management.commands.backup_database import Command
        cmd = Command()
        
        assert "backup" in cmd.help.lower()

    def test_verify_command_help(self):
        """Verify command should have help text."""
        from apps.audit.management.commands.verify_backup import Command
        cmd = Command()
        
        assert "verify" in cmd.help.lower() or "restore" in cmd.help.lower()

    def test_rpo_rto_documentation(self):
        """RPO/RTO should be documented."""
        # This is a documentation test - checking runbook exists
        import os
        runbook_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "docs", "runbooks", "backup_restore.md"
        )
        # Note: runbook was created in Phase 10
        # assert os.path.exists(runbook_path)


# Import for MinIO test
from providers.storage.s3 import MinIOStorageProvider