"""LangSmith tracing decorators for graph nodes and functions."""
import functools
import time
from typing import Callable, Any, Optional
from contextvars import ContextVar

from ai.tracing.config import get_client, is_tracing_enabled, get_project

_current_run_id: ContextVar[Optional[str]] = ContextVar("_current_run_id", default=None)


def get_current_run_id() -> Optional[str]:
    """Get the current LangSmith run ID from context."""
    return _current_run_id.get()


def set_current_run_id(run_id: Optional[str]) -> None:
    """Set the current LangSmith run ID in context."""
    _current_run_id.set(run_id)


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
            started = time.monotonic()

            run = client.create_run(
                name=f"studyai.{node_name}",
                run_type="tool",
                inputs={"args": str(args[1:])[:500] if len(args) > 1 else "state"},
                extra={"node": node_name, "parent_run_id": parent_run_id, **default_metadata},
                project_name=get_project(),
            )
            if run is not None:
                set_current_run_id(run.id)

            try:
                result = func(*args, **kwargs)
                latency_ms = int((time.monotonic() - started) * 1000)
                if run is not None:
                    client.update_run(
                        run.id,
                        outputs={"result": str(result)[:1000] if result else "none"},
                        end_time=None,
                    )
                return result
            except Exception as e:
                latency_ms = int((time.monotonic() - started) * 1000)
                if run is not None:
                    client.update_run(run.id, error=str(e), end_time=None)
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

            started = time.monotonic()
            run = client.create_run(
                name=graph_name,
                run_type="chain",
                inputs={"initial_state": str(args[0])[:500] if args else "none"},
                extra=default_metadata,
                project_name=get_project(),
            )
            previous_run_id = get_current_run_id()
            if run is not None:
                set_current_run_id(run.id)

            try:
                result = func(*args, **kwargs)
                latency_ms = int((time.monotonic() - started) * 1000)
                if run is not None:
                    client.update_run(
                        run.id,
                        outputs={"final_state": str(result)[:1000] if result else "none"},
                        end_time=None,
                    )
                return result
            except Exception as e:
                if run is not None:
                    client.update_run(run.id, error=str(e), end_time=None)
                raise
            finally:
                if run is not None:
                    set_current_run_id(previous_run_id)
        return wrapper
    return decorator