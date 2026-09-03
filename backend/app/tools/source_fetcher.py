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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = httpx.get(
            url,
            timeout=settings.FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers=headers,
        )
        resp.raise_for_status()

        content = resp.text[:settings.MAX_CONTENT_LENGTH_BYTES]

        # Use BeautifulSoup for high quality text extraction
        text, title = _parse_html_bs4(content)

        # Apply Trust Zone 4 security sanitization
        from backend.app.verification.trust_zones import sanitize_untrusted_text
        sanitized_text, _ = sanitize_untrusted_text(text, max_chars=settings.MAX_CONTENT_LENGTH_BYTES)

        return {
            "url": str(resp.url),
            "title": title,
            "text": sanitized_text,
            "content_length": len(sanitized_text),
            "status": "ok",
            "success": True,
        }
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return {
            "url": url,
            "title": "",
            "text": "",
            "content_length": 0,
            "status": f"error: {str(e)[:200]}",
            "success": False,
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
        "success": True,
    }


def _parse_html_bs4(html: str) -> tuple:
    """Extract clean title and visible text from HTML using BeautifulSoup with regex fallback."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove noisy elements
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
            tag.decompose()
            
        title = soup.title.string.strip() if (soup.title and soup.title.string) else ""
        text = soup.get_text(separator=" ", strip=True)
        return text, title
    except Exception:
        import re
        text = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = match.group(1).strip() if match else ""
        return text, title
