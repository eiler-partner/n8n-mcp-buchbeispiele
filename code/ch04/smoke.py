"""Prüft nur den lokalen Kapitel-4-Stack, ohne Anmeldedaten auszugeben."""

import argparse
import json
from pathlib import Path
import subprocess
import urllib.request


LAB = Path(__file__).resolve().parent


def read_port(path: Path = LAB / ".env") -> int:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("LAB_N8N_HOST_PORT="):
            port = int(line.partition("=")[2])
            if not 1 <= port <= 65535:
                raise ValueError("LAB_N8N_HOST_PORT muss zwischen 1 und 65535 liegen")
            return port
    return 15678


def check_health(port: int) -> None:
    # /healthz/readiness meldet erst OK, wenn die Datenbank verbunden und migriert ist.
    url = f"http://127.0.0.1:{port}/healthz/readiness"
    with urllib.request.urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"n8n-Healthcheck: HTTP {response.status}")
        body = response.read(2048)
        if body and body.strip() not in (b'{"status":"ok"}', b"ok"):
            try:
                value = json.loads(body)
            except ValueError as error:
                raise RuntimeError("n8n-Healthcheck liefert kein erwartetes Format") from error
            if value.get("status") != "ok":
                raise RuntimeError("n8n-Healthcheck meldet keinen OK-Status")


def check_database() -> None:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "pg_isready", "-U", "n8n", "-d", "n8n"],
        cwd=LAB, capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode:
        raise RuntimeError("PostgreSQL ist nicht bereit; docker compose ps/logs prüfen")


def check_version() -> None:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "n8n", "n8n", "--version"],
        cwd=LAB, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode or "2.40.7" not in result.stdout:
        raise RuntimeError("n8n-Version weicht von der getesteten Basis 2.40.7 ab")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-only", action="store_true",
                        help="Nur die n8n-HTTP-Adresse prüfen")
    args = parser.parse_args()
    try:
        check_health(read_port())
        if not args.http_only:
            check_database()
            check_version()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FEHLER: {error}")
        return 1
    print("OK: n8n antwortet; PostgreSQL und Version geprüft." if not args.http_only
          else "OK: n8n antwortet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
