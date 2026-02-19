"""Log redaction helpers for sensitive user-provided content."""

from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+?\d[\d\s().-]{7,}\d))")
SECRET_RE = re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{8,}\b")


def redact_text(value: str, max_length: int = 200) -> str:
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", value or "")
    redacted = SECRET_RE.sub("[REDACTED_KEY]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    if len(redacted) > max_length:
        return f"{redacted[:max_length]}..."
    return redacted


def redact_for_log(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(k): redact_for_log(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_for_log(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_log(item) for item in value)
    return value
