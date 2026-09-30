"""Fresh isolated n8n -> Python -> MCP -> three-source briefing test."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15744/webhook/ch44-research"


def compose(env: dict, *args: str, check: bool = True):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args], cwd=ROOT,
                          env=env, text=True, capture_output=True, check=check, timeout=300)


def post(body: dict) -> dict:
    request = urllib.request.Request(WEBHOOK, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=80) as response:
        return json.load(response)


def main():
    env = dict(os.environ, COMPOSE_PROJECT_NAME="buch-ch44-" + secrets.token_hex(4))
    try:
        compose(env, "up", "-d", "--build", "--wait")
        report = post({"action": "run"})
        assert report["path"] == "n8n-mcp-readonly", report
        assert report["status"] == "review_required", report
        assert report["profile"] == {"source_count": 7, "accepted_count": 3,
                                     "blocked_count": 4, "duplicate_groups": 2,
                                     "conflict_metrics": 1, "csv_rows": 2, "csv_missing_cells": 0}, report
        assert report["budget"]["steps"] == 7
        assert report["budget"]["bytes_read"] <= report["budget"]["limits"]["max_bytes"]
        statements = {row["statement_id"]: row for row in report["statements"]}
        assert set(statements) == {"orders", "returns", "delivery_days"}
        assert {claim["value"] for claim in statements["orders"]["claims"]} == {"1198", "1200"}
        for statement in statements.values():
            assert statement["claims"] and statement["text"]
            for claim in statement["claims"]:
                assert claim["evidence"]
                for evidence in claim["evidence"]:
                    assert all(evidence.get(key) for key in ("source_id", "raw_sha256", "locator",
                                                             "retrieved_at_utc", "published_at_utc", "steps"))
        reasons = {row.get("reason") for row in report["sources"] if row["status"] == "blocked"}
        assert reasons == {"robots_disallow", "tdm_reserved", "terms_review_required", "redirect_blocked"}
        audit = compose(env, "exec", "-T", "fixtures", "python", "-c",
                        "import json,urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8144/audit').read().decode())")
        hits = json.loads(audit.stdout)["hits"]  # entries: "<METHOD> <path>"
        paths = {hit.split(" ", 1)[1] for hit in hits}
        assert "/web/private" not in paths and "/web/terms" not in paths, hits
        assert {"GET /api/quarter", "GET /web/briefing", "HEAD /web/tdm", "HEAD /web/redirect"} <= set(hits), hits
        # TDM page and redirect: header-only preflight, never a GET with body.
        assert "GET /web/tdm" not in hits and "GET /web/redirect" not in hits, hits
        artifact = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "n8n_image": "n8nio/n8n:2.40.7", "protocol": "2026-07-28",
                    "fixture_data": "synthetic", "report": report,
                    "fixture_http_requests": hits,
                    "scope": "local read-only teaching pipeline; no legal clearance or external crawling"}
        destination = ROOT / "reports" / "live-observation.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS ch44 live: 3 accepted, 4 blocked, 2 deduplicated, 1 conflict")
    except Exception as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stdout[-3000:] if exc.stdout else "")
            print(exc.stderr[-6000:] if exc.stderr else "")
        print(compose(env, "ps", check=False).stdout)
        print(compose(env, "logs", "--tail", "60", check=False).stdout[-10000:])
        raise
    finally:
        compose(env, "down", "-v", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
