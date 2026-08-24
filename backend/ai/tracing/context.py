"""LangSmith tracing context propagation."""
import contextvars
from typing import Optional

# Context variable to propagate trace/run IDs through async/callback boundaries
trace_context_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "trace_context", default=None
)


class TraceContext:
    """Container for trace context that propagates through the call stack."""

    def __init__(
        self,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.run_id = run_id
        self.trace_id = trace_id
        self.parent_run_id = parent_run_id
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TraceContext":
        return cls(
            run_id=data.get("run_id"),
            trace_id=data.get("trace_id"),
            parent_run_id=data.get("parent_run_id"),
            metadata=data.get("metadata", {}),
        )


def get_trace_context() -> Optional[TraceContext]:
    """Get the current trace context."""
    data = trace_context_var.get()
    if data is None:
        return None
    return TraceContext.from_dict(data)


def set_trace_context(context: Optional[TraceContext]) -> contextvars.Token:
    """Set the trace context and return a token for restoration."""
    if context is None:
        return trace_context_var.set(None)
    return trace_context_var.set(context.to_dict())


def reset_trace_context(token: contextvars.Token) -> None:
    """Reset the trace context using a token from set_trace_context."""
    trace_context_var.reset(token)


class trace_context:
    """Context manager for trace context propagation.

    Usage:
        with trace_context(run_id="abc", trace_id="xyz"):
            # All nested calls will have access to this context
            ...
    """
    def __init__(
        self,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.context = TraceContext(run_id, trace_id, parent_run_id, metadata)
        self.token = None

    def __enter__(self) -> TraceContext:
        self.token = set_trace_context(self.context)
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        reset_trace_context(self.token)


def inject_trace_context(headers: dict) -> dict:
    """Inject trace context into headers for HTTP propagation."""
    context = get_trace_context()
    if context is None:
        return headers

    headers["X-StudyAI-Trace-ID"] = context.trace_id or ""
    headers["X-StudyAI-Run-ID"] = context.run_id or ""
    if context.parent_run_id:
        headers["X-StudyAI-Parent-Run-ID"] = context.parent_run_id
    return headers


def extract_trace_context(headers: dict) -> Optional[TraceContext]:
    """Extract trace context from incoming headers."""
    trace_id = headers.get("X-StudyAI-Trace-ID")
    run_id = headers.get("X-StudyAI-Run-ID")
    parent_run_id = headers.get("X-StudyAI-Parent-Run-ID")

    if not trace_id and not run_id:
        return None

    return TraceContext(
        run_id=run_id or None,
        trace_id=trace_id or None,
        parent_run_id=parent_run_id or None,
    )