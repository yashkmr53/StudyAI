"""LangSmith tracing configuration.

Initializes LangSmith client from environment variables.
Only backend/worker processes should have LANGSMITH_API_KEY set.
"""
import os
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_client: Optional["langsmith.Client"] = None
_tracing_enabled: bool = False


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    global _tracing_enabled
    if not _tracing_enabled:
        try:
            from django.conf import settings
            if hasattr(settings, "LANGSMITH_TRACING"):
                _tracing_enabled = bool(settings.LANGSMITH_TRACING)
            else:
                _tracing_enabled = os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"
        except Exception:
            _tracing_enabled = os.environ.get("LANGSMITH_TRACING", "false").lower() == "true"
    return _tracing_enabled


def get_project() -> str:
    """Get LangSmith project name from environment."""
    return os.environ.get("LANGSMITH_PROJECT", "studyai")


def get_client() -> Optional["langsmith.Client"]:
    """Get or create LangSmith client.

    Returns None if tracing is disabled or client cannot be created.
    """
    global _client
    if not is_tracing_enabled():
        return None

    if _client is None:
        try:
            from langsmith import Client

            api_key = os.environ.get("LANGSMITH_API_KEY")
            if not api_key:
                logger.warning("LANGSMITH_TRACING=true but LANGSMITH_API_KEY not set")
                return None

            project = os.environ.get("LANGSMITH_PROJECT", "studyai")
            _client = Client(api_key=api_key)
            logger.info("LangSmith client initialized (project=%s)", project)
        except Exception as e:
            logger.warning("Failed to initialize LangSmith client: %s", e)
            return None
    return _client


@contextmanager
def trace_context(run_name: str, **metadata):
    """Context manager for manual trace creation.

    Usage:
        with trace_context("studyai.chat", profile_id="...", model="llama3.1:8b"):
            # ... AI workflow ...
    """
    client = get_client()
    if client is None:
        yield None
        return

    try:
        run = client.create_run(
            name=run_name,
            run_type="chain",
            inputs={},
            extra=metadata,
            project_name=get_project(),
        )
        yield run
        client.update_run(run.id, outputs={}, end_time=None)
    except Exception as e:
        logger.warning("LangSmith trace creation failed: %s", e)
        yield None


def traceable(name: str = None, **default_metadata):
    """Decorator to trace a function as a LangSmith run.

    Usage:
        @traceable("studyai.chat.generate", model="llama3.1:8b")
        def generate_answer(...):
            ...
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            client = get_client()
            if client is None:
                return func(*args, **kwargs)

            run_name = name or f"studyai.{func.__module__}.{func.__name__}"
            run = client.create_run(
                name=run_name,
                run_type="tool" if "tool" in func.__name__ else "chain",
                inputs={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                extra=default_metadata,
                project_name=get_project(),
            )
            try:
                result = func(*args, **kwargs)
                client.update_run(run.id, outputs={"result": str(result)[:1000]}, end_time=None)
                return result
            except Exception as e:
                client.update_run(run.id, error=str(e), end_time=None)
                raise
        return wrapper
    return decorator


def log_llm_call(
    *,
    model: str,
    provider: str,
    prompt_name: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error: str = "",
    metadata: dict | None = None,
) -> None:
    """Log an LLM call to LangSmith.

    Called from provider chain after each LLM invocation.
    """
    client = get_client()
    if client is None:
        return

    try:
        client.create_run(
            name=f"studyai.llm.{prompt_name}",
            run_type="llm",
            inputs={"prompt": prompt_name, "version": prompt_version},
            outputs={"tokens": {"input": input_tokens, "output": output_tokens}},
            extra={
                "model": model,
                "provider": provider,
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
                **(metadata or {}),
            },
            project_name=get_project(),
        )
    except Exception as e:
        logger.warning("LangSmith LLM call logging failed: %s", e)


def log_tool_call(
    *,
    tool_name: str,
    arguments: dict,
    result: dict,
    latency_ms: int,
    success: bool,
    error: str = "",
    metadata: dict | None = None,
) -> None:
    """Log a tool call to LangSmith."""
    client = get_client()
    if client is None:
        return

    try:
        client.create_run(
            name=f"studyai.agent.tool.{tool_name}",
            run_type="tool",
            inputs=arguments,
            outputs=result,
            extra={
                "latency_ms": latency_ms,
                "success": success,
                "error": error,
                **(metadata or {}),
            },
            project_name=get_project(),
        )
    except Exception as e:
        logger.warning("LangSmith tool call logging failed: %s", e)


def log_retrieval(
    *,
    query: str,
    profile_id: str,
    subject_id: str | None,
    k: int,
    results_count: int,
    latency_ms: int,
    metadata: dict | None = None,
) -> None:
    """Log a retrieval operation to LangSmith."""
    client = get_client()
    if client is None:
        return

    try:
        import hashlib
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        client.create_run(
            name="studyai.retrieval",
            run_type="retriever",
            inputs={"query_hash": query_hash, "k": k},
            outputs={"results_count": results_count},
            extra={
                "profile_id": profile_id,
                "subject_id": subject_id,
                "latency_ms": latency_ms,
                **(metadata or {}),
            },
            project_name=get_project(),
        )
    except Exception as e:
        logger.warning("LangSmith retrieval logging failed: %s", e)


def flush() -> None:
    """Flush any pending LangSmith runs."""
    client = get_client()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.warning("LangSmith flush failed: %s", e)