"""Serving views for the local object storage provider (§23, §45).

Signed URLs are self-authorizing: possession of a valid, unexpired token
grants exactly one action on exactly one key. With S3 in production these
views disappear (direct-to-bucket uploads/downloads).

Upload additionally enforces file validation (§23): allow-listed content
types and a maximum size.
"""
from django.conf import settings
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from providers.registry import get_object_storage
from shared.exceptions import ValidationError


class StorageUploadView(APIView):
    """PUT target for signed upload URLs. Anonymous by design — the token authorizes."""

    permission_classes = []
    authentication_classes = []
    parser_classes = []

    def put(self, request, key: str):
        storage = get_object_storage()
        payload = storage.verify(request.query_params.get("token", ""), expected_action="upload")
        if payload.get("key") != key:
            from shared.exceptions import Forbidden

            raise Forbidden("Key does not match signed URL.")

        content_type = request.headers.get("Content-Type", "")
        allowed = getattr(settings, "UPLOAD_ALLOWED_CONTENT_TYPES", ["image/jpeg", "image/png", "image/webp"])
        if content_type.split(";")[0].strip() not in allowed:
            raise ValidationError(
                f"Unsupported content type. Allowed: {', '.join(allowed)}.",
                details={"content_type": content_type},
            )

        max_bytes = getattr(settings, "UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
        body = request.body
        if not body:
            raise ValidationError("Empty upload body.")
        if len(body) > max_bytes:
            raise PayloadTooLarge(max_bytes)
        if getattr(settings, "UPLOAD_SNIFF_MAGIC_BYTES", True) and not _magic_matches(body, content_type):
            raise ValidationError("File content does not match its declared type.")

        try:
            size = storage.store_bytes(key, body)
        except ValueError as exc:
            from shared.exceptions import Forbidden

            raise Forbidden(str(exc))
        return Response({"key": key, "size": size})


def PayloadTooLarge(max_bytes: int):
    from shared.exceptions import APIError

    err = APIError("Uploaded file exceeds the size limit.", details={"max_bytes": max_bytes})
    err.status_code = 413
    return err


class StorageDownloadView(APIView):
    """GET target for signed download URLs."""

    permission_classes = []
    authentication_classes = []
    parser_classes = []

    def get(self, request, key: str):
        storage = get_object_storage()
        payload = storage.verify(request.query_params.get("token", ""), expected_action="download")
        if payload.get("key") != key:
            return HttpResponse(status=400)
        data = storage.read_bytes(key)
        return HttpResponse(data, content_type="application/octet-stream")


_MAGIC_SIGNATURES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/webp": b"RIFF",
}


def _magic_matches(body: bytes, content_type: str) -> bool:
    """§23 malicious-upload defense: content must start with the declared
    type's magic bytes (header-based type trust is otherwise spoofable)."""
    sig = _MAGIC_SIGNATURES.get(content_type)
    return sig is None or body.startswith(sig)
