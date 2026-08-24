"""
Source Fetcher — downloads and extracts text from web URLs.

Respects safety budgets: timeout, max content length, robots.txt (optional).
"""
import hashlib
import logging
from typing import Optional, Dict, Any

from backend.app.config.settings import settings

logger = logging.getLogger("app.fetcher")


def fetch_url(url: str) -> Dict[str, Any]:
    """
    Fetch a URL and extract its text content.
    Returns { url, title, text, content_length, status }.
    """
    if settings.SEARCH_PROVIDER == "mock":
        return _mock_fetch(url)

    import httpx
    try:
        resp = httpx.get(
            url,
            timeout=settings.FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "PersonalKnowledgeAgent/0.1"},
        )
        resp.raise_for_status()

        content = resp.text[:settings.MAX_CONTENT_LENGTH_BYTES]

        # Simple HTML → text extraction
        text = _strip_html(content)
        title = _extract_title(content)

        # Apply Trust Zone 4 security sanitization
        from backend.app.verification.trust_zones import sanitize_untrusted_text
        sanitized_text, _ = sanitize_untrusted_text(text, max_chars=settings.MAX_CONTENT_LENGTH_BYTES)

        return {
            "url": str(resp.url),
            "title": title,
            "text": sanitized_text,
            "content_length": len(sanitized_text),
            "status": "ok",
        }
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return {
            "url": url,
            "title": "",
            "text": "",
            "content_length": 0,
            "status": f"error: {str(e)[:200]}",
        }


def _mock_fetch(url: str) -> Dict[str, Any]:
    """Return mock content for offline testing."""
    return {
        "url": url,
        "title": f"Mock page for {url}",
        "text": (
            f"This is mock content fetched from {url}. "
            "It contains simulated information about the topic. "
            "The agent can extract evidence and claims from this text. "
            "Key findings include relevant concepts, relationships, and definitions. "
            "Multiple perspectives are represented in this mock source."
        ),
        "content_length": 300,
        "status": "ok",
    }


def _strip_html(html: str) -> str:
    """Basic HTML tag removal. For production, use BeautifulSoup."""
    import re
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title(html: str) -> str:
    """Extract <title> from HTML."""
    import re
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""
