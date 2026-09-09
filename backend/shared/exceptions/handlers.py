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
import logging
from typing import Optional
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from shared.observability.request_id import get_request_id

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

    def __init__(self, message: Optional[str] = None, *, details: Optional[dict] = None):
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


class ProviderError(APIError):
    status_code = 502
    code = ERROR_PROVIDER_ERROR
    default_message = "Upstream provider failed."


def exception_handler(exc, context):
    """Custom exception handler that wraps DRF's handler with our error envelope."""
    # Handle our custom APIError exceptions first
    if isinstance(exc, APIError):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": get_request_id() or "unknown",
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    # Let DRF handle the exception first
    response = drf_exception_handler(exc, context)

    # If DRF couldn't handle it, return a generic 500
    if response is None:
        logger = logging.getLogger(__name__)
        logger.exception("Unhandled exception", exc_info=exc)
        return Response(
            {
                "error": {
                    "code": ERROR_INTERNAL_ERROR,
                    "message": "An unexpected error occurred.",
                    "request_id": get_request_id() or "unknown",
                    "details": {},
                }
            },
            status=500,
        )

    # Map DRF exception types to our error codes and status codes
    error_code = ERROR_INVALID_REQUEST
    status_code = response.status_code
    
    if hasattr(exc, "default_code"):
        # DRF built-in exceptions
        if exc.default_code == "not_found":
            error_code = ERROR_RESOURCE_NOT_FOUND
        elif exc.default_code == "permission_denied":
            error_code = ERROR_FORBIDDEN
            status_code = 403
        elif exc.default_code == "not_authenticated":
            error_code = ERROR_UNAUTHENTICATED
            status_code = 401
        elif exc.default_code == "throttled":
            error_code = ERROR_RATE_LIMITED
            status_code = 429
        elif exc.default_code == "invalid":
            error_code = ERROR_VALIDATION_ERROR
            status_code = 422
        else:
            error_code = ERROR_INVALID_REQUEST

    # Build our standardized error envelope
    error_data = {
        "error": {
            "code": error_code,
            "message": str(exc) if str(exc) else response.data.get("detail", "Error"),
            "request_id": get_request_id() or "unknown",
            "details": response.data if isinstance(response.data, dict) else {"detail": response.data},
        }
    }

    # Return new response with our envelope
    return Response(error_data, status=status_code)