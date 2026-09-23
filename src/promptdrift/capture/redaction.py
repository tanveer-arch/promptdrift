"""Privacy redaction for captured interactions.

Built-in patterns for email, phone, and API-token-like strings.
Custom redaction callbacks supported.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Built-in redaction patterns
EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
PHONE_PATTERN = r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
API_TOKEN_PATTERN = r"(?:Bearer\s+|sk-|api[_-]?key[=:]\s*)[A-Za-z0-9_\-./]{8,}"

BUILTIN_PATTERNS = {
    "email": EMAIL_PATTERN,
    "phone": PHONE_PATTERN,
    "api_token": API_TOKEN_PATTERN,
}

_REDACTED = "[REDACTED]"


def apply_redaction(
    text: str,
    patterns: list[str] | None = None,
    callback: Callable[[str], str] | None = None,
) -> str:
    """Apply regex patterns and optional callback to redact sensitive data.

    Args:
        text: The text to redact.
        patterns: List of regex pattern strings. Each can be a built-in
            name (``"email"``, ``"phone"``, ``"api_token"``) or a raw regex.
        callback: Optional custom redaction function applied after patterns.

    Returns:
        The redacted text.
    """
    if not text:
        return text

    result = text
    for pattern in patterns or []:
        # Resolve built-in pattern names
        resolved = BUILTIN_PATTERNS.get(pattern, pattern)
        try:
            result = re.sub(resolved, _REDACTED, result)
        except re.error:
            # Invalid regex — skip silently to avoid breaking capture
            pass

    if callback is not None:
        try:
            result = callback(result)
        except Exception:
            # Custom callback failure — skip silently
            pass

    return result
