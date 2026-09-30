from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .contract import snapshot_server, write_snapshot
from .servers import policy_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zeige oder aktualisiere den geprüften MCP-Vertragssnapshot."
    )
    parser.add_argument(
        "--write",
        type=Path,
        help="Snapshot nach fachlichem Review in diese Datei schreiben.",
    )
    args = parser.parse_args()
    snapshot = asyncio.run(snapshot_server(policy_server))
    if args.write is None:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return
    write_snapshot(args.write, snapshot)
    print(f"Snapshot geschrieben: {args.write}")


if __name__ == "__main__":
    main()
