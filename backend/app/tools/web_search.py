"""
Web Search Tool — pluggable search provider.

Providers:
  - "brave"      : Brave Search API (needs BRAVE_SEARCH_API_KEY)
  - "duckduckgo" : Uses duckduckgo-search / ddgs library (free, no key)
  - "tavily"     : Tavily API (needs SEARCH_API_KEY)
  - "mock"       : Returns canned results (no API key needed) — for offline dev only
"""
import uuid
import logging
import time
from typing import List, Dict, Any

import httpx

from backend.app.config.settings import settings

logger = logging.getLogger("app.tools.web_search")


# ---------------------------------------------------------------------------
# Provider Implementations
# ---------------------------------------------------------------------------

def _brave_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using the Brave Search API (requires BRAVE_SEARCH_API_KEY)."""
    api_key = settings.BRAVE_SEARCH_API_KEY.strip()
    if not api_key:
        logger.error("Brave Search API key is not configured. Set BRAVE_SEARCH_API_KEY in .env")
        return []

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            }
            for r in data.get("web", {}).get("results", [])
            if r.get("url")
        ]
        if results:
            logger.info("Brave returned %d results for '%s'", len(results), query)
            return results[:max_results]
        logger.warning("Brave returned 0 results for '%s'", query)
        return []
    except Exception as e:
        logger.error("Brave search failed for '%s': %s", query, e)
        return []


def _duckduckgo_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using the duckduckgo-search / ddgs library (free, no API key)."""
    # Try the new 'ddgs' package first, then fall back to the legacy name
    DDGS = None
    try:
        from ddgs import DDGS as _DDGS
        DDGS = _DDGS
    except ImportError:
        pass
    if DDGS is None:
        try:
            from duckduckgo_search import DDGS as _DDGS
            DDGS = _DDGS
        except ImportError:
            logger.error("Neither 'ddgs' nor 'duckduckgo-search' package is installed. "
                         "Run: pip install ddgs")
            return []

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        results = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw if r.get("href")
        ]
        if results:
            logger.info("DuckDuckGo returned %d results for '%s'", len(results), query)
            return results
        logger.warning("DuckDuckGo returned 0 results for '%s'", query)
        return []
    except Exception as e:
        logger.error("DuckDuckGo search failed for '%s': %s", query, e)
        return []


def _tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using the Tavily API (requires SEARCH_API_KEY)."""
    api_key = settings.SEARCH_API_KEY.strip()
    if not api_key:
        logger.error("Tavily API key is not configured. Set SEARCH_API_KEY in .env")
        return []

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results},
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
        if results:
            logger.info("Tavily returned %d results for '%s'", len(results), query)
            return results
        logger.warning("Tavily returned 0 results for '%s'", query)
        return []
    except Exception as e:
        logger.error("Tavily search failed for '%s': %s", query, e)
        return []


def _mock_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Return placeholder results for offline testing ONLY."""
    logger.warning("⚠️  Using MOCK search — results are fake! Set SEARCH_PROVIDER to 'brave' or 'duckduckgo' in .env")
    return [
        {
            "title": f"Mock result {i+1} for: {query}",
            "url": f"https://example.com/result/{i+1}?q={query.replace(' ', '+')}",
            "snippet": f"This is a mock search snippet for '{query}'. Result {i+1} of {max_results}.",
        }
        for i in range(min(max_results, 3))
    ]


# ---------------------------------------------------------------------------
# Provider chain with automatic fallback (brave → duckduckgo, or vice versa)
# ---------------------------------------------------------------------------

_PROVIDER_FNS = {
    "brave": _brave_search,
    "duckduckgo": _duckduckgo_search,
    "tavily": _tavily_search,
    "mock": _mock_search,
}

# When the primary provider returns nothing, try these in order
_FALLBACK_CHAIN = {
    "brave": ["duckduckgo"],
    "duckduckgo": ["brave"],
    "tavily": ["brave", "duckduckgo"],
}


def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Run a web search using the configured provider.

    If BRAVE_SEARCH_API_KEY is provided, it prioritizes Brave's high-quality
    search index with fallback to DuckDuckGo/Tavily.
    It will NEVER silently return mock/example.com data unless SEARCH_PROVIDER
    is explicitly set to 'mock'.
    """
    provider = settings.SEARCH_PROVIDER
    logger.info("Web search [configured_provider=%s]: %s", provider, query)

    # If explicitly set to mock, use mock (dev only)
    if provider == "mock":
        return _mock_search(query, max_results)

    # If Brave API key is configured, use Brave directly for best results
    if settings.BRAVE_SEARCH_API_KEY.strip():
        results = _brave_search(query, max_results)
        if results:
            return results
        logger.warning("Brave returned 0 results for '%s', checking secondary providers...", query)

    # Try primary provider from settings
    primary_fn = _PROVIDER_FNS.get(provider)
    if primary_fn and provider != "brave":
        results = primary_fn(query, max_results)
        if results:
            return results
        logger.warning("Primary provider '%s' returned no results for '%s', trying fallbacks...", provider, query)

    # Try fallback providers — but NEVER fall back to mock
    for fallback in _FALLBACK_CHAIN.get(provider, ["duckduckgo"]):
        fallback_fn = _PROVIDER_FNS.get(fallback)
        if fallback_fn and fallback != "mock":
            if fallback == "brave" and not settings.BRAVE_SEARCH_API_KEY.strip():
                continue
            logger.info("Trying fallback provider '%s' for '%s'", fallback, query)
            results = fallback_fn(query, max_results)
            if results:
                return results

    # All providers failed — return empty, NOT mock data
    logger.error("ALL search providers returned 0 results for '%s'. No mock fallback.", query)
    return []
