"""LangSmith tracing decorators for graph nodes and functions."""
import functools
from contextvars import ContextVar
from datetime import datetime, timezone as dt_timezone
import time
from typing import Any, Callable, Optional

from ai.tracing.config import _redact_payload, get_client, get_project, is_tracing_enabled

_current_run_id: ContextVar[Optional[str]] = ContextVar("_current_run_id", default=None)


def get_current_run_id() -> Optional[str]:
    """Get the current LangSmith run ID from context."""
    return _current_run_id.get()


def set_current_run_id(run_id: Optional[str]) -> None:
    """Set the current LangSmith run ID in context."""
    _current_run_id.set(run_id)


def _safe_redacted_dict(payload: Any, fallback_key: str) -> dict:
    redacted = _redact_payload(payload)
    if isinstance(redacted, dict):
        return redacted
    return {fallback_key: redacted}


def traced_node(node_name: str, **default_metadata):
    """Decorator for LangGraph nodes to create child runs.

    Usage:
        @traced_node("retrieve_evidence", feature="chat")
        def retrieve_node(state: ChatState) -> ChatState:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not is_tracing_enabled():
                return func(*args, **kwargs)

            client = get_client()
            if client is None:
                return func(*args, **kwargs)

            parent_run_id = get_current_run_id()
            raw_inputs = args[0] if (args and isinstance(args[0], dict)) else {"args": list(args), "kwargs": kwargs}
            redacted_inputs = _safe_redacted_dict(raw_inputs, "input")
            create_kwargs = dict(
                name=f"studyai.{node_name}",
                run_type="tool",
                inputs=redacted_inputs,
                extra={"node": node_name, **default_metadata},
                project_name=get_project(),
                start_time=datetime.now(dt_timezone.utc),
            )
            if parent_run_id:
                create_kwargs["parent_run_id"] = parent_run_id

            run = None
            try:
                run = client.create_run(**create_kwargs)
            except Exception:
                run = None
            if run is not None:
                set_current_run_id(run.id)

            try:
                result = func(*args, **kwargs)
                if run is not None:
                    raw_out = result if isinstance(result, dict) else {"result": result}
                    client.update_run(
                        run.id,
                        outputs=_safe_redacted_dict(raw_out, "result"),
                        end_time=datetime.now(dt_timezone.utc),
                    )
                return result
            except Exception as e:
                if run is not None:
                    redacted_err = _redact_payload({"text": str(e)}).get("text", "[REDACTED]")
                    client.update_run(run.id, error=str(redacted_err), end_time=datetime.now(dt_timezone.utc))
                raise
            finally:
                if run is not None:
                    set_current_run_id(parent_run_id)
        return wrapper
    return decorator


def traced_graph(graph_name: str, **default_metadata):
    """Decorator for graph invocation to create a parent run.

    Usage:
        @traced_graph("studyai.chat", feature="chat")
        def invoke_chat_graph(state: ChatState) -> ChatState:
            return chat_graph.invoke(state)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not is_tracing_enabled():
                return func(*args, **kwargs)

            client = get_client()
            if client is None:
                return func(*args, **kwargs)

            previous_run_id = get_current_run_id()
            raw_inputs = args[0] if (args and isinstance(args[0], dict)) else {"initial_state": args[0] if args else None, "kwargs": kwargs}
            create_kwargs = dict(
                name=graph_name,
                run_type="chain",
                inputs=_safe_redacted_dict(raw_inputs, "initial_state"),
                extra=default_metadata,
                project_name=get_project(),
                start_time=datetime.now(dt_timezone.utc),
            )
            if previous_run_id:
                create_kwargs["parent_run_id"] = previous_run_id

            run = None
            try:
                run = client.create_run(**create_kwargs)
            except Exception:
                run = None
            if run is not None:
                set_current_run_id(run.id)

            try:
                result = func(*args, **kwargs)
                if run is not None:
                    raw_out = result if isinstance(result, dict) else {"final_state": result}
                    client.update_run(
                        run.id,
                        outputs=_safe_redacted_dict(raw_out, "final_state"),
                        end_time=datetime.now(dt_timezone.utc),
                    )
                return result
            except Exception as e:
                if run is not None:
                    redacted_err = _redact_payload({"text": str(e)}).get("text", "[REDACTED]")
                    client.update_run(run.id, error=str(redacted_err), end_time=datetime.now(dt_timezone.utc))
                raise
            finally:
                if run is not None:
                    set_current_run_id(previous_run_id)
        return wrapper
    return decorator