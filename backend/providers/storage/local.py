"""Local filesystem object storage for v1 development (§23, §24).

Production swaps in an S3-compatible implementation behind the same
ObjectStorageProvider protocol. URLs are "signed" by HMAC so they expire
and cannot be forged without the secret key.

Byte-level helpers (store_bytes/read_bytes/exists) back the local serving
views in providers.storage.views; with S3 these views disappear in favor of
direct-to-bucket uploads.
"""
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner


class LocalObjectStorage:
    def _root(self) -> Path:
        root = Path(settings.OBJECT_STORAGE_LOCAL_DIR)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _safe_path(self, key: str) -> Path:
        path = (self._root() / key).resolve()
        if not str(path).startswith(str(self._root().resolve())):
            raise ValueError("Invalid object key.")
        return path

    def create_upload_url(self, key: str, *, content_type: str, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds if ttl_seconds is not None else settings.SIGNED_URL_TTL_SECONDS
        return self._sign("upload", key, ttl, content_type=content_type)

    def create_download_url(self, key: str, *, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds if ttl_seconds is not None else settings.SIGNED_URL_TTL_SECONDS
        return self._sign("download", key, ttl)

    def delete(self, key: str) -> None:
        self._safe_path(key).unlink(missing_ok=True)

    def store_bytes(self, key: str, data: bytes) -> int:
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return len(data)

    def read_bytes(self, key: str) -> bytes:
        return self._safe_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._safe_path(key).exists()

    def size(self, key: str) -> int:
        return self._safe_path(key).stat().st_size

    @staticmethod
    def verify(token: str, expected_action: str | None = None) -> dict:
        signer = TimestampSigner()
        try:
            payload = signer.unsign_object(token, max_age=settings.SIGNED_URL_TTL_SECONDS)
        except (BadSignature, SignatureExpired) as exc:
            from shared.exceptions import Forbidden

            raise Forbidden("Signed URL is invalid or expired.") from exc
        if expected_action and payload.get("action") != expected_action:
            from shared.exceptions import Forbidden

            raise Forbidden("Signed URL action mismatch.")
        return payload

    def _sign(self, action: str, key: str, ttl_seconds: int, *, content_type: str | None = None) -> str:
        signer = TimestampSigner()
        payload = {"action": action, "key": key}
        if content_type:
            payload["content_type"] = content_type
        token = signer.sign_object(payload)
        digest = hmac_digest(settings.SECRET_KEY, f"{action}:{key}")
        return f"/api/v1/storage/{action}/{quote(key)}?token={token}&sig={digest}"


def hmac_digest(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:12]
