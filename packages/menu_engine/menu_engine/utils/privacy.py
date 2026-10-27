"""Privacy and PII redaction utilities.

Preserves customer privacy when sending transcripts or summaries to external providers (LLMs, STT, TTS).
"""

from __future__ import annotations

import re

# Phone numbers (international, formatted, or contiguous 10-15 digits)
_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4,6}|\b(?:\+?\d{10,15})\b"
)

# Email addresses
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)

# Credit card numbers (13-19 digits with optional spaces or dashes)
_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{1,4}\b"
)


def redact_pii(text: str) -> str:
    """Mask personally identifiable information (phone numbers, emails, credit cards).

    Used when passing transcripts, summaries, or prompts to external AI providers.
    """
    if not text:
        return text

    # Redact credit cards first before phone numbers
    redacted = _CARD_PATTERN.sub("[CARD_REDACTED]", text)
    redacted = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", redacted)
    redacted = _PHONE_PATTERN.sub("[PHONE_REDACTED]", redacted)
    return redacted
