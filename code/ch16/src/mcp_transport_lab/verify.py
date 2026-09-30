"""Echte lokale Wire-Prüfung: Subprozess, HTTP und absichtlicher Versionsfehler."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mcp import Client, StdioServerParameters


def free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_server(port: int, process: subprocess.Popen[bytes]) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"HTTP-Server endete mit {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("HTTP-Server wurde nicht bereit")


async def check_stdio() -> dict[str, str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_transport_lab.server", "--transport", "stdio"],
    )
    async with Client(params, mode="2026-07-28") as client:
        names = [tool.name for tool in (await client.list_tools()).tools]
        result = await client.call_tool("echo_ticket", {"ticket_id": "LAB-15"})
    assert names == ["echo_ticket"]
    assert result.structured_content == {"ticket_id": "LAB-15", "status": "checked"}
    return result.structured_content


def request_wrong_version(url: str) -> tuple[int, dict]:
    body = {
        "jsonrpc": "2.0",
        "id": "wrong-version",
        "method": "tools/list",
        "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": "1900-01-01",
            "io.modelcontextprotocol/clientInfo": {"name": "ch16-probe", "version": "1.0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }},
    }
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "1900-01-01",
            "Mcp-Method": "tools/list",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


async def check_http() -> tuple[dict[str, str], int, dict]:
    port = free_loopback_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_transport_lab.server", "--transport", "http", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(port, process)
        url = f"http://127.0.0.1:{port}/mcp"
        async with Client(url, mode="2026-07-28") as client:
            names = [tool.name for tool in (await client.list_tools()).tools]
            result = await client.call_tool("echo_ticket", {"ticket_id": "LAB-15"})
        assert names == ["echo_ticket"]
        assert result.structured_content == {"ticket_id": "LAB-15", "status": "checked"}
        status, payload = await asyncio.to_thread(request_wrong_version, url)
        assert status == 400, (status, payload)
        assert payload["error"]["code"] == -32022, payload
        return result.structured_content, status, payload
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


async def verify() -> dict:
    stdio = await check_stdio()
    http, status, error = await check_http()
    assert stdio == http
    return {
        "stdio": stdio,
        "http": http,
        "wrong_version_http_status": status,
        "wrong_version_rpc_code": error["error"]["code"],
    }


def main() -> None:
    print(json.dumps(asyncio.run(verify()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
