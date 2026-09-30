from __future__ import annotations

import json
import logging
import re
from typing import Any


LOGGER = logging.getLogger("ch24.audit")
SECRET_FIELD = re.compile(r"(authorization|token|secret|password|signature)", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SECRET_FIELD.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def audit(event: str, **fields: Any) -> None:
    payload = {"event": event, **redact(fields)}
    LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
