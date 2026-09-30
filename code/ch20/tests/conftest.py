from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcp_auth_lab.token_cli import issue_fixture_token


@dataclass(frozen=True)
class LiveServer:
    url: str
    issuer: str
    resource: str
    secret: str
    audit_path: Path

    def token(
        self,
        *,
        subject: str = "alice",
        tenant: str = "tenant-a",
        scope: str = "documents:read",
        consent: str = "granted",
        audience: str | None = None,
        issuer: str | None = None,
        lifetime_seconds: int = 300,
    ) -> str:
        return issue_fixture_token(
            subject=subject,
            tenant=tenant,
            scope=scope,
            consent=consent,
            issuer=issuer or self.issuer,
            audience=audience or self.resource,
            client_id="pytest-client",
            secret=self.secret,
            lifetime_seconds=lifetime_seconds,
        )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveServer]:
    port = _free_port()
    issuer = "http://127.0.0.1:9019"
    resource = f"http://127.0.0.1:{port}/mcp"
    secret = "pytest-chapter-20-fixture-secret-at-least-32-bytes"
    audit_path = tmp_path_factory.mktemp("audit") / "events.jsonl"
    env = os.environ.copy()
    env.update(
        {
            "MCP_AUTH_HOST": "127.0.0.1",
            "MCP_AUTH_PORT": str(port),
            "MCP_AUTH_ISSUER": issuer,
            "MCP_AUTH_RESOURCE": resource,
            "MCP_JWT_FIXTURE_SECRET": secret,
            "MCP_AUDIT_PATH": str(audit_path),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_auth_lab.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"MCP test server stopped early:\n{stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("MCP test server did not open its port")

    try:
        yield LiveServer(resource, issuer, resource, secret, audit_path)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
