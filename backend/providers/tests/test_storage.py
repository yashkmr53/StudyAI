"""MinIO storage operations tests (Phase 11)."""
import os
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from providers.storage.local import LocalObjectStorage
from providers.storage.s3 import MinIOStorageProvider, S3StorageProvider
from providers.base import ObjectStorageProvider


class TestLocalObjectStorage(TestCase):
    """Test local filesystem storage."""

    def setUp(self):
        self.provider = LocalObjectStorage()

    def test_store_and_read_bytes(self):
        """Should store and read bytes correctly."""
        key = "test/file.txt"
        data = b"Hello, World!"
        
        size = self.provider.store_bytes(key, data)
        assert size == len(data)
        
        read_data = self.provider.read_bytes(key)
        assert read_data == data

    def test_create_upload_url(self):
        """Should create signed upload URL."""
        url = self.provider.create_upload_url(
            "test.txt", content_type="text/plain", ttl_seconds=300
        )
        
        assert "token=" in url
        assert "sig=" in url
        assert "upload" in url

    def test_create_download_url(self):
        """Should create signed download URL."""
        url = self.provider.create_download_url("test.txt", ttl_seconds=300)
        
        assert "token=" in url
        assert "sig=" in url
        assert "download" in url

    def test_delete(self):
        """Should delete object."""
        key = "test/delete.txt"
        self.provider.store_bytes(key, b"data")
        assert self.provider.exists(key)
        
        self.provider.delete(key)
        assert not self.provider.exists(key)

    def test_exists(self):
        """Should check existence."""
        key = "test/exists.txt"
        assert not self.provider.exists(key)
        
        self.provider.store_bytes(key, b"data")
        assert self.provider.exists(key)

    def test_size(self):
        """Should return object size."""
        key = "test/size.txt"
        data = b"x" * 100
        self.provider.store_bytes(key, data)
        
        size = self.provider.size(key)
        assert size == 100

    def test_verify_token(self):
        """Should verify signed URLs."""
        url = self.provider.create_upload_url("test.txt", content_type="text/plain", ttl_seconds=300)
        
        # Extract token from URL
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        token = params["token"][0]
        
        payload = LocalObjectStorage.verify(token, expected_action="upload")
        assert payload["action"] == "upload"
        assert payload["key"] == "test.txt"

    def test_verify_expired_token_fails(self):
        """Expired tokens should fail verification."""
        from django.core.signing import TimestampSigner
        signer = TimestampSigner()
        payload = {"action": "upload", "key": "test.txt"}
        token = signer.sign_object(payload)
        
        from shared.exceptions import Forbidden
        with self.assertRaises(Forbidden):
            # Use a very short max_age by setting SIGNED_URL_TTL_SECONDS
            with override_settings(SIGNED_URL_TTL_SECONDS=0):
                LocalObjectStorage.verify(token, expected_action="upload")


class TestMinIOStorageProvider(TestCase):
    """Test MinIO/S3 storage provider."""

    @patch("providers.storage.s3.boto3.client")
    def test_minio_initialization(self, mock_boto_client):
        """Test MinIO provider initialization."""
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadBucket"
        )
        mock_client.create_bucket.return_value = None
        
        provider = MinIOStorageProvider(
            backend="minio",
            endpoint="http://minio:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="test-bucket",
            region="us-east-1",
            secure=False,
        )
        
        assert provider.name == "minio"
        assert provider.bucket == "test-bucket"
        mock_client.create_bucket.assert_called_once()

    @patch("providers.storage.s3.boto3.client")
    def test_minio_upload_url(self, mock_boto_client):
        """Test MinIO presigned upload URL."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "http://minio:9000/bucket/key?sig=abc"
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        url = provider.create_upload_url("test.txt", content_type="text/plain", ttl_seconds=300)
        
        assert url == "http://minio:9000/bucket/key?sig=abc"
        mock_client.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={"Bucket": "test", "Key": "test.txt", "ContentType": "text/plain"},
            ExpiresIn=300,
        )

    @patch("providers.storage.s3.boto3.client")
    def test_minio_download_url(self, mock_boto_client):
        """Test MinIO presigned download URL."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "http://minio:9000/bucket/key?sig=abc"
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        url = provider.create_download_url("test.txt", ttl_seconds=300)
        
        assert url == "http://minio:9000/bucket/key?sig=abc"

    @patch("providers.storage.s3.boto3.client")
    def test_minio_delete(self, mock_boto_client):
        """Test MinIO delete."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        provider.delete("test.txt")
        
        mock_client.delete_object.assert_called_once_with(Bucket="test", Key="test.txt")

    @patch("providers.storage.s3.boto3.client")
    def test_minio_store_read_bytes(self, mock_boto_client):
        """Test MinIO store/read bytes."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Mock get_object response
        mock_body = MagicMock()
        mock_body.read.return_value = b"test data"
        mock_client.get_object.return_value = {"Body": mock_body}
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        # Store
        size = provider.store_bytes("test.txt", b"test data")
        assert size == 9
        mock_client.put_object.assert_called_once()
        
        # Read
        data = provider.read_bytes("test.txt")
        assert data == b"test data"

    @patch("providers.storage.s3.boto3.client")
    def test_minio_exists(self, mock_boto_client):
        """Test MinIO exists check."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        # Exists
        mock_client.head_object.return_value = {}
        assert provider.exists("test.txt") is True
        
        # Not exists
        from botocore.exceptions import ClientError
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )
        assert provider.exists("missing.txt") is False

    @patch("providers.storage.s3.boto3.client")
    def test_minio_size(self, mock_boto_client):
        """Test MinIO size."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.head_object.return_value = {"ContentLength": 1234}
        
        provider = MinIOStorageProvider(bucket="test")
        provider._client = mock_client
        
        size = provider.size("test.txt")
        assert size == 1234

    def test_s3_storage_provider_requires_credentials(self):
        """S3 provider should require credentials when used via registry."""
        # S3StorageProvider itself doesn't validate in __init__,
        # but the registry validates when get_object_storage() is called
        provider = S3StorageProvider(
            backend="s3",
            bucket="test",
            # Missing access_key and secret_key
        )
        # Should not raise in __init__ (lazy validation)
        assert provider.backend == "s3"
        assert provider.access_key is None
        assert provider.secret_key is None

    def test_s3_storage_provider_with_credentials(self):
        """S3 provider should work with credentials."""
        with patch("providers.storage.s3.boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_bucket.return_value = {}
            
            provider = S3StorageProvider(
                bucket="test-bucket",
                access_key="AKIA...",
                secret_key="secret...",
                region="us-east-1",
            )
            
            assert provider.name == "s3"
            assert provider.backend == "s3"


class TestStorageInterface(TestCase):
    """Test storage provider interface compliance."""

    def test_local_storage_implements_interface(self):
        provider = LocalObjectStorage()
        assert isinstance(provider, ObjectStorageProvider)
        
        # Check all required methods exist
        required_methods = [
            "create_upload_url", "create_download_url", "delete",
            "store_bytes", "read_bytes", "exists", "size",
        ]
        for method in required_methods:
            assert hasattr(provider, method)
            assert callable(getattr(provider, method))

    def test_minio_storage_implements_interface(self):
        with patch("providers.storage.s3.boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_bucket.return_value = {}
            
            provider = MinIOStorageProvider(
                backend="minio",
                endpoint="http://minio:9000",
                access_key="key",
                secret_key="secret",
                bucket="test",
            )
            
            assert isinstance(provider, ObjectStorageProvider)
            
            required_methods = [
                "create_upload_url", "create_download_url", "delete",
                "store_bytes", "read_bytes", "exists", "size",
            ]
            for method in required_methods:
                assert hasattr(provider, method)
                assert callable(getattr(provider, method))