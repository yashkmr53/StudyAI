"""Shared uploaded object size and magic-byte validation helpers."""
import logging
from typing import Iterable, Optional

from django.conf import settings

from shared.exceptions import ValidationError

logger = logging.getLogger(__name__)

MAGIC_SIGNATURES: dict[str, bytes] = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
    "application/pdf": b"%PDF-",
}


def magic_matches(body: bytes, content_type: str) -> bool:
    """Verify binary header matches the declared MIME type."""
    sig = MAGIC_SIGNATURES.get(content_type)
    if sig is None:
        return True
    if not body.startswith(sig):
        return False
    if content_type == "image/webp" and len(body) >= 12:
        return body[8:12] == b"WEBP"
    return True


def has_allowed_magic_bytes(
    body: bytes,
    *,
    allowed_types: Optional[Iterable[str]] = None,
    source_type: Optional[str] = None,
) -> bool:
    """Check whether uploaded object bytes start with an allowed image/PDF signature."""
    if source_type == "pdf":
        return magic_matches(body, "application/pdf")
    types = list(
        allowed_types
        or getattr(settings, "UPLOAD_ALLOWED_CONTENT_TYPES", ["image/jpeg", "image/png", "image/webp"])
    )
    return any(magic_matches(body, ct) for ct in types)


def _cleanup_invalid_object(storage, key: str) -> None:
    try:
        storage.delete(key)
    except Exception as exc:  # noqa: BLE001 — validation error takes precedence
        logger.warning("Failed to delete rejected upload object %s: %s", key, exc)


def validate_uploaded_object(storage, key: str, *, source_type: Optional[str] = None) -> bytes:
    """Validate size and magic bytes of a stored object (e.g. post-presigned PUT).

    Checks storage.size(key) prior to reading bytes into memory to prevent OOM
    on oversized uploads and deletes rejected objects from storage.
    """
    if not key or not storage.exists(key):
        raise ValidationError("No uploaded object found for this page.")

    max_bytes = int(getattr(settings, "UPLOAD_MAX_BYTES", 10 * 1024 * 1024))
    if hasattr(storage, "size"):
        reported_size = storage.size(key)
        if reported_size <= 0:
            _cleanup_invalid_object(storage, key)
            raise ValidationError("Uploaded file is empty.")
        if reported_size > max_bytes:
            _cleanup_invalid_object(storage, key)
            raise ValidationError("Uploaded file exceeds the size limit.")

    data = storage.read_bytes(key)
    if not data:
        _cleanup_invalid_object(storage, key)
        raise ValidationError("Uploaded file is empty.")
    if len(data) > max_bytes:
        _cleanup_invalid_object(storage, key)
        raise ValidationError("Uploaded file exceeds the size limit.")

    if getattr(settings, "UPLOAD_SNIFF_MAGIC_BYTES", True) and not has_allowed_magic_bytes(
        data, source_type=source_type
    ):
        _cleanup_invalid_object(storage, key)
        raise ValidationError("Uploaded file content is not a supported image or PDF format.")

    return data
