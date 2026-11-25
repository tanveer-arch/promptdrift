"""Privacy redaction for captured interactions.

Built-in patterns for email, phone, and API-token-like strings.
Custom redaction callbacks supported.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Callable

# Built-in redaction patterns
EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
PHONE_PATTERN = r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
API_TOKEN_PATTERN = r"(?:Bearer\s+|sk-|api[_-]?key[=:]\s*)[A-Za-z0-9_\-./]{8,}"
CREDIT_CARD_PATTERN = (
    r"\b(?:"
    r"4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4}"  # Visa (13-16 digits)
    r"|5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # MasterCard (16 digits)
    r"|2[2-7]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # MasterCard 2xxx series
    r"|3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}"  # American Express (15 digits)
    r"|6(?:011|5\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Discover
    r"|\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{1,7}"  # Generic delimited cards (13-19 digits)
    r")\b"
)
SSN_PATTERN = r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"

BUILTIN_PATTERNS = {
    "email": EMAIL_PATTERN,
    "phone": PHONE_PATTERN,
    "api_token": API_TOKEN_PATTERN,
    "credit_card": CREDIT_CARD_PATTERN,
    "ssn": SSN_PATTERN,
}

_REDACTED = "[REDACTED]"


class RedactionWarning(UserWarning):
    """Warning emitted when a redaction rule or callback fails."""


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
        except re.error as exc:
            warnings.warn(
                f"Skipping invalid redaction pattern '{pattern}': {exc}",
                RedactionWarning,
            )

    if callback is not None:
        try:
            result = callback(result)
        except Exception as exc:
            warnings.warn(
                f"Redaction callback raised {type(exc).__name__}: {exc}",
                RedactionWarning,
            )

    return result
