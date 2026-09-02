"""Mock web search provider (development/tests only).

Produces deterministic, schema-valid web search results. The pipeline
machinery around it (retrieval, schemas, citations, verification) is
real code. This mock exists so unit tests are deterministic and do not
require network access.
"""
import hashlib
import json

from providers.web.base import WebSearchResult


class MockWebSearchProvider:
    """Deterministic mock web search.

    Returns results derived from the query hash so tests are stable.
    The URLs/domains are clearly mock data so they can never be mistaken
    for real citations.
    """
    name = "mock-web"

    def search(self, query: str, *, max_results: int = 5, request_id: str = "") -> list[WebSearchResult]:
        query = (query or "").strip()
        if not query:
            return []

        results: list[WebSearchResult] = []
        # Deterministic seed from query
        seed = int(hashlib.md5(query.encode()).hexdigest(), 16)

        templates = [
            ("{query} — Wikipedia", "https://en.wikipedia.org/wiki/{slug}"),
            ("{query} tutorial — Real Python", "https://realpython.com/{slug}/"),
            ("Understanding {query} — GeeksforGeeks", "https://www.geeksforgeeks.org/{slug}/"),
            ("{query} — Official Documentation", "https://docs.example.com/{slug}"),
            ("{query} explained — Medium", "https://medium.com/@author/{slug}-explained"),
        ]

        slug = query.lower().replace(" ", "-")
        for i, (title_tmpl, url_tmpl) in enumerate(templates):
            if i >= max_results:
                break
            # Vary the slug slightly per result to avoid identical URLs
            result_slug = f"{slug}-{i}" if i > 0 else slug
            title = title_tmpl.format(query=query.title(), slug=result_slug)
            url = url_tmpl.format(slug=result_slug)
            snippet = (
                f"Mock search result {i + 1} for '{query}'. "
                f"This is deterministic mock content for testing citation pipelines. "
                f"It discusses core concepts and provides examples."
            )
            results.append(WebSearchResult(
                title=title,
                url=url,
                snippet=snippet,
            ))

        return results
