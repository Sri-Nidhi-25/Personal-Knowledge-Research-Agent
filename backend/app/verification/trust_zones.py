"""
Trust Zone 4: Security & Untrusted Content Isolation.

According to System Specification Document 10 (Security & Isolation Model):
All external web content, search snippets, and ingested documents are
classified as Trust Zone 4 (Untrusted).

Defenses:
1. Strip prompt injection triggers (e.g., 'ignore previous instructions', system overrides).
2. Clean invisible control characters and zero-width characters.
3. Wrap untrusted text in strict XML delimiter boundaries.
4. Enforce hard truncation limits before LLM reasoning.
"""
import re
import unicodedata
from typing import Tuple, Dict, Any

# Common prompt injection patterns in untrusted web content
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the|in)?\s*(developer mode|unrestricted|jailbroken|system administrator)", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[\s*system\s*\]", re.IGNORECASE),
    re.compile(r"###\s*instruction\s*:", re.IGNORECASE),
    re.compile(r"new\s+(rule|directive|instruction)\s*:", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(above|instructions|rules)", re.IGNORECASE),
]

_ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u0000-\u0008\u000E-\u001F]")


def sanitize_untrusted_text(raw_text: str, max_chars: int = 50000) -> Tuple[str, bool]:
    """
    Sanitize untrusted text from Zone 4 (web / user docs).
    Returns (sanitized_text, has_injection_signals).
    """
    if not raw_text:
        return "", False

    # 1. Normalize Unicode and strip zero-width / control characters
    text = unicodedata.normalize("NFKC", raw_text)
    text = _ZERO_WIDTH_CHARS.sub(" ", text)

    # 2. Check for prompt injection signatures
    has_injection_signals = False
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            has_injection_signals = True
            # Neutralize the match by replacing with a sanitized token
            text = pat.sub("[REDACTED_INSTRUCTION_OVERRIDE]", text)

    # 3. Truncate to safe character length
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[TRUNCATED TO MAXIMUM SAFE LENGTH]"

    return text.strip(), has_injection_signals


def wrap_in_untrusted_boundary(
    content: str,
    source_id: str,
    source_type: str = "web_page",
    max_chars: int = 25000
) -> str:
    """
    Wrap untrusted source content in strict XML-style delimiters for safe LLM prompting.
    """
    clean_text, flagged = sanitize_untrusted_text(content, max_chars=max_chars)
    flag_notice = ' injection_flagged="true"' if flagged else ""
    return (
        f'<untrusted_source id="{source_id}" type="{source_type}"{flag_notice}>\n'
        f"{clean_text}\n"
        f"</untrusted_source>"
    )
