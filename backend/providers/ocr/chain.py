"""OCR provider chain: primary attempt then fallback attempt (§28).

A logical OCR job may contain a primary attempt plus a fallback attempt;
this chain is that mechanism. Business logic sees a single provider.
"""
import logging
import time

from providers.base import OCRProvider, OCRResult

logger = logging.getLogger(__name__)


def record_ocr_call(*, provider: str, latency_ms: int, success: bool, error: str = "") -> None:
    """Best-effort OCR provider usage telemetry (§25). Never raises."""
    try:
        from apps.audit.models import ProviderCallLog

        ProviderCallLog.objects.create(
            provider=provider,
            model="",
            latency_ms=latency_ms,
            success=success,
            error=error[:500],
        )
    except Exception:  # noqa: BLE001 — telemetry must not break the pipeline
        logger.warning("ocr provider call log write failed", exc_info=True)


class OCRChainProvider:
    name = "chain"

    def __init__(self, providers: list[OCRProvider]):
        if not providers:
            raise ValueError("OCR chain requires at least one provider.")
        self.providers = providers

    def recognize(self, image_uri: str, *, request_id: str) -> tuple[OCRResult, list[str]]:
        """Returns (result, attempted_provider_names). Raises if all fail."""
        attempted: list[str] = []
        last_error: Exception | None = None
        for provider in self.providers:
            attempted.append(provider.name)
            started = time.monotonic()
            try:
                result = provider.recognize(image_uri, request_id=request_id)
                result.provider = result.provider or provider.name
                record_ocr_call(
                    provider=provider.name,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    success=True,
                )
                return result, attempted
            except Exception as exc:  # noqa: BLE001 — provider failures are expected
                last_error = exc
                record_ocr_call(
                    provider=provider.name,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    success=False,
                    error=str(exc)[:300],
                )
        from shared.exceptions import ProviderError

        raise ProviderError(
            "All OCR providers failed.",
            details={"attempted": attempted, "last_error": str(last_error)},
        )
