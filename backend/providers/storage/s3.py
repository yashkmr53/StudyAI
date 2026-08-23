"""MinIO / S3-compatible object storage provider (Phase 11).

Implements ObjectStorageProvider protocol using MinIO (local) or S3 (production).
Uses boto3 for S3-compatible API.
"""
import logging
import os
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from providers.base import ObjectStorageProvider

logger = logging.getLogger(__name__)


class MinIOStorageProvider:
    """MinIO / S3-compatible object storage provider.
    
    Works with MinIO (local development) and AWS S3 (production).
    Selected via STORAGE_BACKEND environment variable.
    
    Environment variables:
        STORAGE_BACKEND: "minio" or "s3"
        MINIO_ENDPOINT: MinIO endpoint URL (default: http://minio:9000)
        MINIO_ACCESS_KEY: MinIO access key (default: minioadmin)
        MINIO_SECRET_KEY: MinIO secret key (default: minioadmin)
        MINIO_BUCKET: Bucket name (default: studyai)
        MINIO_REGION: Region (default: us-east-1)
        MINIO_SECURE: Use HTTPS (default: false for MinIO)
        
        S3_ENDPOINT: S3 endpoint URL (for S3-compatible)
        S3_BUCKET: S3 bucket name
        S3_REGION: AWS region (default: us-east-1)
        S3_ACCESS_KEY: AWS access key
        S3_SECRET_KEY: AWS secret key
        S3_SECURE: Use HTTPS (default: true for S3)
    
    The same interface works for both MinIO and S3.
    """
    
    def __init__(
        self,
        *,
        backend: str | None = None,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        secure: bool | None = None,
        fail: bool = False,
        name: str = "minio",
    ):
        self.name = name
        self.fail = fail
        self.backend = backend or os.environ.get("STORAGE_BACKEND", "minio")
        
        if self.backend == "s3":
            self.endpoint = endpoint or os.environ.get("S3_ENDPOINT")
            self.access_key = access_key or os.environ.get("S3_ACCESS_KEY")
            self.secret_key = secret_key or os.environ.get("S3_SECRET_KEY")
            self.bucket = bucket or os.environ.get("S3_BUCKET", "studyai")
            self.region = region or os.environ.get("S3_REGION", "us-east-1")
            self.secure = secure if secure is not None else os.environ.get("S3_SECURE", "true").lower() == "true"
        else:  # minio
            self.endpoint = endpoint or os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
            self.access_key = access_key or os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
            self.secret_key = secret_key or os.environ.get("MINIO_SECRET_KEY", "minioadmin")
            self.bucket = bucket or os.environ.get("MINIO_BUCKET", "studyai")
            self.region = region or os.environ.get("MINIO_REGION", "us-east-1")
            self.secure = secure if secure is not None else os.environ.get("MINIO_SECURE", "false").lower() == "true"
        
        self._client = None
        self._ensure_bucket()
        
        logger.info(
            "MinIO/S3 storage initialized (backend=%s, endpoint=%s, bucket=%s, region=%s)",
            self.backend, self.endpoint, self.bucket, self.region
        )
    
    def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                use_ssl=self.secure,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3},
                ),
            )
        return self._client
    
    def _ensure_bucket(self) -> None:
        """Ensure bucket exists."""
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                try:
                    client = self._get_client()
                    if self.region == "us-east-1":
                        client.create_bucket(Bucket=self.bucket)
                    else:
                        client.create_bucket(
                            Bucket=self.bucket,
                            CreateBucketConfiguration={"LocationConstraint": self.region},
                        )
                    logger.info("Created bucket: %s", self.bucket)
                except ClientError:
                    logger.exception("Failed to create bucket")
            elif error_code == "403":
                logger.warning("No permission to access bucket: %s", self.bucket)
            else:
                logger.warning("Bucket check failed: %s", e)
        except NoCredentialsError:
            logger.warning("No credentials for MinIO/S3")
        except Exception as e:
            logger.warning("Bucket check failed: %s", e)
    
    def create_upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> str:
        """Generate presigned URL for upload."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        client = self._get_client()
        try:
            url = client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=ttl_seconds,
            )
            return url
        except ClientError as e:
            logger.exception("Failed to generate upload URL")
            raise RuntimeError(f"Failed to generate upload URL: {e}") from e
    
    def create_download_url(self, key: str, *, ttl_seconds: int) -> str:
        """Generate presigned URL for download."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        client = self._get_client()
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                },
                ExpiresIn=ttl_seconds,
            )
            return url
        except ClientError as e:
            logger.exception("Failed to generate download URL")
            raise RuntimeError(f"Failed to generate download URL: {e}") from e
    
    def delete(self, key: str) -> None:
        """Delete an object."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        client = self._get_client()
        try:
            client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            logger.exception("Failed to delete object")
            raise RuntimeError(f"Failed to delete object: {e}") from e
    
    def store_bytes(self, key: str, data: bytes) -> int:
        """Store bytes directly."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        client = self._get_client()
        try:
            client.put_object(Bucket=self.bucket, Key=key, Body=data)
            return len(data)
        except ClientError as e:
            logger.exception("Failed to store bytes")
            raise RuntimeError(f"Failed to store bytes: {e}") from e
    
    def read_bytes(self, key: str) -> bytes:
        """Read bytes directly."""
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated provider failure")
        
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"Object not found: {key}")
            logger.exception("Failed to read bytes")
            raise RuntimeError(f"Failed to read bytes: {e}") from e
    
    def exists(self, key: str) -> bool:
        """Check if object exists."""
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.exception("Failed to check object existence")
            raise RuntimeError(f"Failed to check object existence: {e}") from e
    
    def size(self, key: str) -> int:
        """Get object size."""
        client = self._get_client()
        try:
            response = client.head_object(Bucket=self.bucket, Key=key)
            return response["ContentLength"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise FileNotFoundError(f"Object not found: {key}")
            logger.exception("Failed to get object size")
            raise RuntimeError(f"Failed to get object size: {e}") from e


class S3StorageProvider(MinIOStorageProvider):
    """Alias for S3 backend - uses same implementation with S3 defaults."""
    
    def __init__(self, **kwargs):
        kwargs.setdefault("backend", "s3")
        kwargs.setdefault("name", "s3")
        super().__init__(**kwargs)