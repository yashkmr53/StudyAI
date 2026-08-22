"""API error contract (architecture §61).

Every error response uses the envelope:

    {
      "error": {
        "code": "...",
        "message": "...",
        "request_id": "req_...",
        "details": {}
      }
    }
"""
from rest_framework.views import exception_handler as drf_exception_handler

ERROR_INVALID_REQUEST = "INVALID_REQUEST"
ERROR_UNAUTHENTICATED = "UNAUTHENTICATED"
ERROR_FORBIDDEN = "FORBIDDEN"
ERROR_RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
ERROR_SESSION_LOCK_LOST = "SESSION_LOCK_LOST"
ERROR_IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
ERROR_REVISION_CONFLICT = "REVISION_CONFLICT"
ERROR_VALIDATION_ERROR = "VALIDATION_ERROR"
ERROR_RATE_LIMITED = "RATE_LIMITED"
ERROR_INTERNAL_ERROR = "INTERNAL_ERROR"
ERROR_PROVIDER_ERROR = "PROVIDER_ERROR"
ERROR_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class APIError(Exception):
    """Base class for domain errors carrying a stable machine-readable code."""

    status_code = 400
    code = ERROR_INVALID_REQUEST
    default_message = "Invalid request."

    def __init__(self, message: str | None = None, *, details: dict | None = None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details or {}


class Unauthenticated(APIError):
    status_code = 401
    code = ERROR_UNAUTHENTICATED
    default_message = "Authentication credentials were not provided."


class Forbidden(APIError):
    status_code = 403
    code = ERROR_FORBIDDEN
    default_message = "You do not have access to this resource."


class ResourceNotFound(APIError):
    status_code = 404
    code = ERROR_RESOURCE_NOT_FOUND
    default_message = "Resource not found."


class SessionLockLost(APIError):
    status_code = 409
    code = ERROR_SESSION_LOCK_LOST
    default_message = "The canvas session is now controlled by another device."


class IdempotencyConflict(APIError):
    status_code = 409
    code = ERROR_IDEMPOTENCY_CONFLICT
    default_message = "Request conflicts with an already-processed idempotent request."


class RevisionConflict(APIError):
    status_code = 409
    code = ERROR_REVISION_CONFLICT
    default_message = "The resource was modified concurrently."


class ValidationError(APIError):
    status_code = 422
    code = ERROR_VALIDATION_ERROR
    default_message = "Validation failed."


class RateLimited(APIError):
    status_code = 429
    code = ERROR_RATE_LIMITED
    default_message = "Too many requests."


class ProviderUnavailable(APIError):
    status_code = 503
    code = ERROR_PROVIDER_UNAVAILABLE
    default_message = "An external provider is temporarily unavailable."


_STATUS_TO_CODE = {
    400: ERROR_INVALID_REQUEST,
    401: ERROR_UNAUTHENTICATED,
    403: ERROR_FORBIDDEN,
    404: ERROR_RESOURCE_NOT_FOUND,
    405: ERROR_INVALID_REQUEST,
    406: ERROR_INVALID_REQUEST,
    409: ERROR_REVISION_CONFLICT,
    415: ERROR_INVALID_REQUEST,
    429: ERROR_RATE_LIMITED,
    500: ERROR_INTERNAL_ERROR,
    502: ERROR_PROVIDER_ERROR,
    503: ERROR_PROVIDER_UNAVAILABLE,
}


def exception_handler(exc, context):
    from rest_framework.exceptions import ValidationError as DRFValidationError
    from shared.observability.request_id import get_request_id

    if isinstance(exc, DRFValidationError) and not isinstance(exc, APIError):
        exc = ValidationError(details=exc.detail)

    response = drf_exception_handler(exc, context)
    request_id = get_request_id() or "req_unknown"

    if response is None:
        if isinstance(exc, APIError):
            return _error_response(exc.status_code, exc.code, exc.message, exc.details, request_id)
        return None

    details = getattr(response, "data", None)
    if isinstance(details, dict) and set(details.keys()) == {"error"}:
        return response

    if isinstance(exc, APIError):
        return _error_response(exc.status_code, exc.code, exc.message, exc.details, request_id)

    code = _STATUS_TO_CODE.get(response.status_code, ERROR_INTERNAL_ERROR)
    message = _summarize(details)
    return _error_response(response.status_code, code, message, details, request_id)


def _error_response(status, code, message, details, request_id):
    from rest_framework.response import Response

    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details if isinstance(details, dict) else {},
        }
    }
    return Response(payload, status=status)


def _summarize(details) -> str:
    if isinstance(details, dict):
        for key in ("detail", "non_field_errors"):
            value = details.get(key)
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
        first = next(iter(details.items()), None)
        if first:
            field, value = first
            if isinstance(value, list) and value:
                return f"{field}: {value[0]}"
            return f"{field}: {value}"
    return "Request failed."
