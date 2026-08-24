"""
Web Search Tool — pluggable search provider.

Providers:
  - "mock"       : Returns canned results (no API key needed)
  - "duckduckgo" : Uses duckduckgo-search library (free, no key)
  - "tavily"     : Tavily API (needs SEARCH_API_KEY)
"""
import uuid
from typing import List, Dict, Any
from backend.app.config.settings import settings


def _mock_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Return placeholder results for offline testing."""
    return [
        {
            "title": f"Mock result {i+1} for: {query}",
            "url": f"https://example.com/result/{i+1}?q={query.replace(' ', '+')}",
            "snippet": f"This is a mock search snippet for '{query}'. Result {i+1} of {max_results}.",
        }
        for i in range(min(max_results, 3))
    ]


def _duckduckgo_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using the duckduckgo-search library."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise RuntimeError("duckduckgo-search not installed. Run: pip install duckduckgo-search")

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    return [
        {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
        for r in raw
    ]


def _tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using the Tavily API."""
    import httpx
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": settings.SEARCH_API_KEY, "query": query, "max_results": max_results},
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Run a web search using the configured provider."""
    provider = settings.SEARCH_PROVIDER
    if provider == "duckduckgo":
        return _duckduckgo_search(query, max_results)
    if provider == "tavily":
        return _tavily_search(query, max_results)
    return _mock_search(query, max_results)
