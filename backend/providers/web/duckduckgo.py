"""DuckDuckGo web search provider (real web retrieval).

Uses the duckduckgo_search library to perform real web searches without
requiring an API key. Results carry authoritative metadata (title, URL,
domain) that originates from the actual search result and must never be
fabricated by the LLM.

Falls back gracefully when the network is unavailable so the chat
pipeline can still answer from uploaded material.
"""
import logging
import time

from providers.web.base import WebSearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoWebSearchProvider:
    """Real web search via DuckDuckGo.

    No API key required. Returns results with real URLs, titles, and
    domains. If the search fails (network, rate-limit, block), returns
    an empty list so the pipeline degrades gracefully.
    """
    name = "duckduckgo"

    def __init__(self, *, max_results: int = 5, timeout: int = 15, region: str = "wt-wt"):
        self.max_results = max_results
        self.timeout = timeout
        self.region = region

    def search(self, query: str, *, max_results: int = 5, request_id: str = "") -> list[WebSearchResult]:
        query = (query or "").strip()
        if not query:
            return []

        k = min(max_results, self.max_results)
        started = time.monotonic()

        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=self.timeout) as ddgs:
                raw = list(ddgs.text(query, max_results=k, region=self.region))

            results = []
            for r in raw:
                title = r.get("title", "")
                url = r.get("href", "")
                snippet = r.get("body", "") or r.get("snippet", "")
                if not url:
                    continue
                results.append(WebSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                ))

            latency_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "DuckDuckGo search returned %d results for query (%.20s) in %dms",
                len(results), query, latency_ms,
            )
            return results

        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "DuckDuckGo search failed after %dms: %s",
                latency_ms, exc,
            )
            return []
