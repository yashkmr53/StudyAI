"""LLM provider fallback chain (architecture §28).

Mirrors OCRChainProvider: primary attempt → fallback attempt(s) →
ProviderUnavailable. Every attempt is recorded in ProviderCallLog for
observability (§25).
"""
import logging
import time

from django.db import transaction

from providers.base import LLMProvider, Prompt, StructuredLLMResult

logger = logging.getLogger(__name__)


def record_provider_call(*, provider: str, model: str, latency_ms: int, success: bool, error: str = "") -> None:
    """Best-effort provider usage telemetry (§25). Never raises."""
    try:
        from apps.audit.models import ProviderCallLog

        ProviderCallLog.objects.create(
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            success=success,
            error=error[:500],
        )
    except Exception:  # noqa: BLE001 — telemetry must not break the pipeline
        logger.warning("provider call log write failed", exc_info=True)


class LLMChainProvider:
    name = "llm-chain"

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("LLM chain requires at least one provider.")
        self.providers = providers

    def generate_structured(self, *, prompt: Prompt, schema=None, request_id: str) -> StructuredLLMResult:
        attempted: list[str] = []
        last_error: Exception | None = None
        for provider in self.providers:
            attempted.append(provider.name)
            started = time.monotonic()
            try:
                result = provider.generate_structured(prompt=prompt, schema=schema, request_id=request_id)
                record_provider_call(
                    provider=provider.name,
                    model=getattr(result, "model", ""),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    success=True,
                )
                result.attempted_providers = attempted  # type: ignore[attr-defined]
                return result
            except Exception as exc:  # noqa: BLE001 — fallback is the point
                last_error = exc
                record_provider_call(
                    provider=provider.name,
                    model="",
                    latency_ms=int((time.monotonic() - started) * 1000),
                    success=False,
                    error=str(exc)[:300],
                )
                logger.warning("LLM provider %s failed: %s", provider.name, exc)

        from shared.exceptions import ProviderUnavailable

        raise ProviderUnavailable(
            "All LLM providers failed.",
            details={"attempted": attempted, "last_error": str(last_error)},
        )
