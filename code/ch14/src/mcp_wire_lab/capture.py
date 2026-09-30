"""Sendet sichtbare JSON-RPC-Frames an einen echten SDK-Serverprozess."""

from __future__ import annotations

import argparse
import json
import select
import subprocess
import sys
from pathlib import Path
from typing import Any

VERSIONS = {"legacy": "2025-11-25", "modern": "2026-07-28"}
METHOD = "tools/call"
ARGUMENTS = {"document_id": "DOC-101"}


def _read_line(process: subprocess.Popen[str], seconds: int = 10) -> dict[str, Any]:
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], seconds)
    if not ready:
        raise TimeoutError("Keine Antwort des lokalen MCP-Servers")
    line = process.stdout.readline()
    if not line:
        detail = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"Server beendete stdout: {detail[:500]}")
    return json.loads(line)


def capture(era: str) -> dict[str, Any]:
    if era not in VERSIONS:
        raise ValueError(f"Unbekannte Ära: {era}")
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_wire_lab.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    frames: list[dict[str, Any]] = []

    def send(message: dict[str, Any], response: bool = True) -> dict[str, Any] | None:
        assert process.stdin is not None
        frames.append({"direction": "client->server", "message": message})
        process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        process.stdin.flush()
        if not response:
            return None
        answer = _read_line(process)
        frames.append({"direction": "server->client", "message": answer})
        return answer

    try:
        if era == "legacy":
            init = send({
                "jsonrpc": "2.0", "id": "init-1", "method": "initialize",
                "params": {
                    "protocolVersion": VERSIONS[era], "capabilities": {},
                    "clientInfo": {"name": "Kapitel-14-Rohclient", "version": "1.0.0"},
                },
            })
            if not init or "error" in init:
                raise RuntimeError(f"Legacy-Initialisierung fehlgeschlagen: {init}")
            send({"jsonrpc": "2.0", "method": "notifications/initialized"}, response=False)
            params: dict[str, Any] = {"name": "read_policy", "arguments": ARGUMENTS}
        else:
            meta = {
                "io.modelcontextprotocol/protocolVersion": VERSIONS[era],
                "io.modelcontextprotocol/clientInfo": {
                    "name": "Kapitel-14-Rohclient", "version": "1.0.0"
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            }
            discovery = send({
                "jsonrpc": "2.0", "id": "discover-1", "method": "server/discover",
                "params": {"_meta": meta},
            })
            if not discovery or "error" in discovery:
                raise RuntimeError(f"Moderne Discovery fehlgeschlagen: {discovery}")
            params = {"name": "read_policy", "arguments": ARGUMENTS, "_meta": meta}
        result = send({"jsonrpc": "2.0", "id": "call-1", "method": METHOD, "params": params})
        if not result or "error" in result:
            raise RuntimeError(f"Toolaufruf fehlgeschlagen: {result}")
        return {"era": era, "protocol_version": VERSIONS[era], "frames": frames}
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("era", choices=sorted(VERSIONS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    trace = capture(args.era)
    content = json.dumps(trace, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Trace geschrieben: {args.output}")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
