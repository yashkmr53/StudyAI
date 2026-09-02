"""Web search provider abstraction (architecture §24, web retrieval).

Business logic depends on the WebSearchProvider protocol only; the
underlying search SDK must never leak into apps. This follows the same
pattern as LLMProvider / OCRProvider / EmbeddingProvider.
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class WebSearchResult:
    """A single web search result with authoritative metadata.

    The URL and title originate from the actual retrieval result and
    must never be fabricated by the LLM.
    """
    title: str
    url: str
    snippet: str
    domain: str = ""
    source_type: str = "web"

    def __post_init__(self):
        if not self.domain and self.url:
            from urllib.parse import urlparse
            try:
                self.domain = urlparse(self.url).netloc or ""
            except Exception:
                self.domain = ""

    def as_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet[:280],
            "domain": self.domain,
        }


@runtime_checkable
class WebSearchProvider(Protocol):
    def search(self, query: str, *, max_results: int, request_id: str) -> list[WebSearchResult]: ...
