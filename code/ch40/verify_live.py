"""Isolierter Live-Nachweis mit automatischem Abbau nur des eigenen Stacks."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15741/webhook/ch40-trace"
TELEMETRY = "http://127.0.0.1:8140"


def post(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def compose(env: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args],
                          cwd=ROOT, env=env, text=True, capture_output=True,
                          check=check, timeout=300)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="buch-ch40-secrets-") as directory:
        secret_dir = Path(directory)
        for name in ("db_password", "n8n_key"):
            path = secret_dir / name
            path.write_text(secrets.token_urlsafe(40), encoding="utf-8")
            path.chmod(0o600)
        env = dict(os.environ, CH40_SECRETS_DIR=directory,
                   COMPOSE_PROJECT_NAME="buch-ch40-" + secrets.token_hex(4))
        try:
            config = compose(env, "config").stdout
            for name in ("db_password", "n8n_key"):
                assert (secret_dir / name).read_text() not in config
            compose(env, "up", "-d", "--build", "--wait")
            post(TELEMETRY + "/reset", {})
            observations = []
            for label, extra in (("normal", {}), ("lost_correlation", {"break_trace": True}),
                                 ("model_error", {"model_error": True})):
                request_id = "ch40-" + uuid.uuid4().hex[:12]
                correlation_id = uuid.uuid4().hex
                response = post(WEBHOOK, {"request_id": request_id,
                                          "correlation_id": correlation_id, **extra})
                assert response["request_id"] == request_id
                report = get(TELEMETRY + "/report/" + request_id)
                observations.append({"case": label, "response": response, "trace": report})
            normal, lost, failed = observations
            assert normal["trace"]["complete"] and normal["trace"]["business_ok"]
            assert normal["response"]["usage"]["synthetic_cost_micro_usd"] == 48
            assert normal["trace"]["stages"] == ["n8n", "mcp", "retrieval", "model"]
            assert not lost["trace"]["complete"]
            assert "correlation_broken" in lost["trace"]["faults"]
            assert failed["trace"]["complete"] and not failed["trace"]["business_ok"]
            sli = get(TELEMETRY + "/sli")
            assert (sli["good"], sli["total"], sli["bad"],
                    sli["unverifiable"], sli["known_failed"]) == (1, 3, 2, 1, 1)
            with urllib.request.urlopen("http://127.0.0.1:15741/metrics", timeout=10) as result:
                metrics_excerpt = result.read(100000).decode()
                assert result.status == 200 and "n8n" in metrics_excerpt
            report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "n8n_image": "n8nio/n8n:2.40.7", "model": "synthetic-fixed-fixture",
                      "mcp_transport": "stdio-via-http-bridge", "sli": sli,
                      "checks": ["n8n_webhook", "mcp_initialize", "mcp_tools_list",
                                 "mcp_tools_call", "retrieval_fixture", "model_fixture",
                                 "correlation_loss_detected", "business_error_detected",
                                 "internal_metrics_endpoint"], "cases": observations}
            path = ROOT / "reports" / "live-observation.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
            print("PASS ch40 live: 4 layers, lost trace, model error, SLI 1/3")
        except Exception as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                print(exc.stdout[-4000:] if exc.stdout else "")
                print(exc.stderr[-8000:] if exc.stderr else "")
            print(compose(env, "ps", check=False).stdout)
            print(compose(env, "logs", "--tail", "80", check=False).stdout[-12000:])
            raise
        finally:
            compose(env, "down", "-v", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
