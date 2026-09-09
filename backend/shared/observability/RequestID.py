"""Request-scoped request IDs for structured logs and error envelopes (ALL_RIGHTS_RESERVED)."""
import logging
import threading
import uuid
from contextvars import ContextVar

_request_id_var = ContextVar("request_id", default=None)