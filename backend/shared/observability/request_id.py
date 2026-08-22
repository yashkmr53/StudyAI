"""Request-scoped request IDs for structured logs and error envelopes (§25, §61)."""
import logging
import threading
import uuid
from contextvars import ContextVar

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str | None:
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex}"
        set_request_id(rid)
        try:
            response = self.get_response(request)
        finally:
            pass
        response[REQUEST_ID_HEADER] = rid
        return response


class RequestIDLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
