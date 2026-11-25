"""Request-scoped request IDs for structured logs and error envelopes (§25, §61)."""
import logging
import threading
import uuid
from contextvars import ContextVar
from typing import Optional

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


class RequestIDMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def _begin_request(self, request):
        rid = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex}"
        return rid, _request_id_var.set(rid)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)
        rid, token = self._begin_request(request)
        try:
            response = self.get_response(request)
        finally:
            _request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = rid
        return response

    async def __acall__(self, request):
        rid, token = self._begin_request(request)
        try:
            response = await self.get_response(request)
        finally:
            _request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = rid
        return response


class RequestIDLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
