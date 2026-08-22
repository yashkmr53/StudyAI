"""OCR provider chain: primary attempt then fallback attempt (§28).

A logical OCR job may contain a primary attempt plus a fallback attempt;
this chain is that mechanism. Business logic sees a single provider.
"""
from providers.base import OCRProvider, OCRResult


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
            try:
                result = provider.recognize(image_uri, request_id=request_id)
                result.provider = result.provider or provider.name
                return result, attempted
            except Exception as exc:  # noqa: BLE001 — provider failures are expected
                last_error = exc
        from shared.exceptions import ProviderUnavailable

        raise ProviderUnavailable(
            "All OCR providers failed.",
            details={"attempted": attempted, "last_error": str(last_error)},
        )
