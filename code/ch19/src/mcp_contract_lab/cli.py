from __future__ import annotations

import argparse
import asyncio
import json

from .client import ClientPool, ServerBinding


async def run(url: str) -> None:
    binding = ServerBinding(
        alias="policy",
        target=url,
        allowed_tools=frozenset({"search_policies", "check_documents"}),
        cache_partition="policy-demo",
    )
    async with ClientPool((binding,)) as clients:
        result = await clients.call_tool(
            "policy/search_policies",
            {"query": "Informationsschutz", "limit": 3},
        )
        print(json.dumps(result.model_dump(by_alias=True, mode="json"), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Kapitel-19-MCP-Client")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
