from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .domain import AuditEvent


class AuditSink(Protocol):
    def record(self, run_id: str, event: AuditEvent) -> None: ...


class NullAuditSink:
    def record(self, run_id: str, event: AuditEvent) -> None:
        return None


class JsonlAuditSink:
    """Append-only demonstration sink; production should use durable central storage."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, run_id: str, event: AuditEvent) -> None:
        row = {"run_id": run_id, **event.model_dump(mode="json")}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
