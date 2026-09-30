from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from .models import ToolContract


def canonical_contracts(contracts: Iterable[ToolContract]) -> str:
    payload = [contract.model_dump(mode="json") for contract in contracts]
    payload.sort(key=lambda item: item["name"])
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def manifest_digest(contracts: Iterable[ToolContract]) -> str:
    return hashlib.sha256(canonical_contracts(contracts).encode()).hexdigest()


def proposal_digest(tool: str, tenant_id: str, arguments: dict[str, object]) -> str:
    canonical = json.dumps(
        {"arguments": arguments, "tenant_id": tenant_id, "tool": tool},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
