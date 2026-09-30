from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"CANARY-[A-Z0-9-]+"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*\S+"),
)


def redact(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
