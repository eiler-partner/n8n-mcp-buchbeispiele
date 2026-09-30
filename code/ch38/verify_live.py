"""Eigenständiger Kapitel-38-Live-Test; räumt nur seinen Compose-Stack ab."""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "https://localhost:15738"
# Deliberately forged forwarded values. The Caddyfile sets no trusted_proxies, so Caddy must
# ignore all three and set its own values (Caddy docs, reverse_proxy, "Defaults").
SPOOFED = {"X-Forwarded-For": "203.0.113.66", "X-Forwarded-Host": "spoofed.example",
           "X-Forwarded-Proto": "http"}


def forwarded_findings(seen: dict, host: str) -> list[str]:
    """Violations of the expected Caddy behaviour without trusted_proxies (empty list = pass)."""
    findings = []
    chain = [part.strip() for part in (seen.get("X-Forwarded-For") or "").split(",")]
    if SPOOFED["X-Forwarded-For"] in chain:
        findings.append("X-Forwarded-For contains the forged client address")
    if len(chain) != 1:
        findings.append("X-Forwarded-For is not a single address")
    else:
        try:
            ipaddress.ip_address(chain[0])
        except ValueError:
            findings.append("X-Forwarded-For is not an IP address")
    if seen.get("X-Forwarded-Host") != host:
        findings.append(f"X-Forwarded-Host is not the request host {host}")
    if seen.get("X-Forwarded-Proto") != "https":
        findings.append("X-Forwarded-Proto is not https")
    return findings


def command(*args: str, env: dict[str, str], capture: bool = False) -> str:
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, check=True,
                            capture_output=capture, timeout=240)
    return result.stdout if capture else ""


def generate_secrets(folder: Path) -> dict[str, str]:
    values = {"db_password": secrets.token_urlsafe(40),
              "n8n_key": secrets.token_urlsafe(48),
              "runner_token": secrets.token_urlsafe(48)}
    for name, value in values.items():
        path = folder / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
        # The temp parent remains 0700; Docker's non-root image users need
        # read access to the bind-mounted secret files inside their containers.
        path.chmod(0o644)
    return values


def https_json(path: str, context: ssl.SSLContext, body: dict | None = None,
               headers: dict[str, str] | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(URL + path, data=data, headers=headers or {})
    with urllib.request.urlopen(request, context=context, timeout=60) as response:
        assert response.status == 200
        return json.load(response)


def main() -> None:
    private = Path(tempfile.mkdtemp(prefix="buch-ch38-", dir="/private/tmp"))
    private.chmod(0o700)
    env = dict(os.environ, CH38_SECRET_DIR=str(private),
               COMPOSE_PROJECT_NAME=f"buch-ch38-check-{secrets.token_hex(4)}")
    values = generate_secrets(private)
    started = False
    try:
        config_raw = command("docker", "compose", "--profile", "probe", "config", "--format", "json",
                             env=env, capture=True)
        config = json.loads(config_raw)
        assert all(value not in config_raw for value in values.values())
        assert config["services"]["caddy"]["ports"][0]["host_ip"] == "127.0.0.1"
        assert all("ports" not in config["services"][name]
                   for name in ("n8n", "postgres", "runners", "probe"))

        started = True
        try:
            command("docker", "compose", "--profile", "probe", "up", "-d", "--wait", env=env)
        except subprocess.CalledProcessError:
            subprocess.run(("docker", "compose", "--profile", "probe", "logs", "--tail", "50"),
                           cwd=ROOT, env=env, text=True, check=False, timeout=30)
            raise
        ca_path = private / "local-root.crt"
        for attempt in range(15):
            try:
                command("docker", "compose", "cp", "caddy:/data/caddy/pki/authorities/local/root.crt",
                        str(ca_path), env=env)
                break
            except subprocess.CalledProcessError:
                if attempt == 14:
                    raise
                time.sleep(1)
        context = ssl.create_default_context(cafile=str(ca_path))
        context.check_hostname = True

        # Authenticated TLS handshake: no -k / CERT_NONE and no host trust-store mutation.
        connection = http.client.HTTPSConnection("localhost", 15738, context=context, timeout=30)
        # http.client sends "Host: localhost:15738"; Caddy must copy it into X-Forwarded-Host.
        connection.request("GET", "/lab/headers", headers={
            "Mcp-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call",
            "Mcp-Name": "synthetic_probe", **SPOOFED})
        response = connection.getresponse()
        certificate = connection.sock.getpeercert()
        headers = json.load(response)
        connection.close()
        assert headers["Mcp-Protocol-Version"] == "2026-07-28"
        assert headers["Mcp-Method"] == "tools/call"
        assert headers["Mcp-Name"] == "synthetic_probe"
        findings = forwarded_findings(headers, "localhost:15738")
        assert not findings, (findings, headers)

        last_error = None
        for _ in range(30):
            try:
                workflow = https_json("/webhook/ch38-probe", context,
                                      {"ping": "synthetic"},
                                      {"Content-Type": "application/json"})
                if workflow == {"ok": True, "runner": "external", "echo": "synthetic"}:
                    break
                last_error = f"unexpected workflow output: {workflow!r}"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)
        else:
            raise AssertionError(f"external Python runner did not answer: {last_error}")

        stream = http.client.HTTPSConnection("localhost", 15738, context=context, timeout=20)
        stream.request("GET", "/lab/events")
        event_response = stream.getresponse()
        assert event_response.status == 200
        assert event_response.getheader("Content-Type") == "text/event-stream"
        first = event_response.readline()
        at_first = time.monotonic()
        assert first == b"data: first\n", f"first SSE line: {first!r}"
        event_response.readline()  # blank separator
        second = event_response.readline()
        at_second = time.monotonic()
        assert second == b"data: second\n", f"second SSE line: {second!r}"
        assert at_second - at_first >= 0.4, "proxy buffered the SSE response"
        stream.close()

        for service in ("n8n", "postgres", "runners", "caddy", "probe"):
            container_id = command("docker", "compose", "--profile", "probe", "ps", "-q", service,
                                   env=env, capture=True).strip()
            inspect = command("docker", "inspect", container_id, env=env, capture=True)
            assert all(value not in inspect for value in values.values()), service
        workflow_raw = (ROOT / "n8n/ch38-probe.json").read_text(encoding="utf-8")
        assert all(value not in workflow_raw for value in values.values())

        report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "n8n_image": "n8nio/n8n:2.40.7", "runner_image": "n8nio/runners:2.40.7",
                  "tls": {"verified_with_local_ca": True, "subject": certificate.get("subject"),
                          "issuer": certificate.get("issuer"), "not_after": certificate.get("notAfter")},
                  "workflow": workflow, "mcp_headers": {key: headers[key] for key in
                                                    ("Mcp-Protocol-Version", "Mcp-Method", "Mcp-Name")},
                  "forwarded_headers": {"sent": SPOOFED, "seen_by_probe": {key: headers[key] for key in
                                        ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto")}},
                  "stream_gap_seconds": round(at_second - at_first, 3),
                  "checks": ["loopback_only", "no_secret_values_in_config_or_inspect",
                             "local_ca_tls_verification", "forwarded_header_sanitization",
                             "python_external_runner", "sse_flush"]}
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports/live-observation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS chapter 38 live: TLS, isolation, secrets, external Python runner, SSE")
    finally:
        try:
            if started:
                command("docker", "compose", "--profile", "probe", "down", "-v", env=env)
        finally:
            shutil.rmtree(private)


if __name__ == "__main__":
    main()
