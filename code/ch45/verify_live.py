"""Fresh n8n/MCP/reviewer end-to-end test with a disposable Compose project."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from case_service import issue_token

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15745/webhook/ch45-review"


def compose(env: dict, *args: str, check: bool = True):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args],
                          cwd=ROOT, env=env, text=True, capture_output=True,
                          check=check, timeout=300)


def call(payload: dict) -> dict:
    request = urllib.request.Request(WEBHOOK, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def review_payload(case: dict, token: str, decision: str, accepted: list[str]) -> dict:
    report = case["report"]
    return {"action": "review", "case_id": case["case_id"], "reviewer_token": token,
            "decision": decision, "comment": "Synthetische Befunde fachlich zur Sichtung übernommen.",
            "accepted_open_ids": accepted,
            "report_sha256": report["report_sha256"],
            "catalog_sha256": report["catalog_sha256"],
            "document_set_sha256": report["document_set_sha256"]}


def main():
    signing_key = secrets.token_urlsafe(48)
    env = dict(os.environ, CH45_SIGNING_KEY=signing_key,
               COMPOSE_PROJECT_NAME="buch-ch45-" + secrets.token_hex(4))
    os.environ["CH45_SIGNING_KEY"] = signing_key
    requester = issue_token("synthetic-owner", "requester")
    reviewer = issue_token("synthetic-compliance", "reviewer")
    self_reviewer = issue_token("synthetic-owner", "reviewer")
    checks = {}
    try:
        compose(env, "up", "-d", "--build", "--wait")
        case = call({"action": "start", "requester_token": requester,
                     "catalog_uri": "catalog://supplier-review/v1"})
        assert case["ok"] and case["status"] == "draft", case
        report = case["report"]
        assert {row["control_id"]: row["status"] for row in report["controls"]} == {
            "C01": "fulfilled", "C02": "partial", "C03": "not_evidenced",
            "C04": "not_applicable", "C05": "fulfilled", "C06": "partial"}
        assert "contradictory_documents" in report["controls"][5]["flags"]
        assert all(item["raw_sha256"] and item["locator"] for control in report["controls"]
                   for item in control["evidence"])
        pre = call({"action": "export", "case_id": case["case_id"],
                    "requester_token": requester})
        checks["preapproval_export"] = pre["code"]
        assert pre == {"ok": False, "code": "export_requires_approval"}
        self_try = call(review_payload(case, self_reviewer, "approve", report["open_control_ids"]))
        checks["self_approval"] = self_try["code"]
        assert self_try["code"] == "self_approval_forbidden"
        stale = review_payload(case, reviewer, "approve", report["open_control_ids"])
        stale["catalog_sha256"] = "0" * 64
        stale_result = call(stale)
        checks["stale_basis"] = stale_result["code"]
        assert stale_result["code"] == "stale_review_basis"
        incomplete = call(review_payload(case, reviewer, "approve", ["C02"]))
        checks["missing_open_findings"] = incomplete["code"]
        assert incomplete["code"] == "open_findings_not_acknowledged"
        decision = call(review_payload(case, reviewer, "approve", report["open_control_ids"]))
        assert decision["ok"] and decision["status"] == "approved"
        exported = call({"action": "export", "case_id": case["case_id"],
                         "requester_token": requester})
        assert exported["ok"] and exported["status"] == "exported"
        assert exported["artifact"]["report"]["report_sha256"] == report["report_sha256"]
        replay = call({"action": "export", "case_id": case["case_id"],
                       "requester_token": requester})
        checks["export_replay"] = replay["code"]
        assert replay["code"] == "export_requires_approval"
        rejected_case = call({"action": "start", "requester_token": requester})
        rejection = call(review_payload(rejected_case, reviewer, "reject", []))
        assert rejection["status"] == "rejected"
        rejected_export = call({"action": "export", "case_id": rejected_case["case_id"],
                                "requester_token": requester})
        checks["rejected_export"] = rejected_export["code"]
        assert rejected_export["code"] == "export_requires_approval"
        observed = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "n8n_image": "n8nio/n8n:2.40.7", "protocol": "2026-07-28",
                    "data": "synthetic", "model": "deterministic_fixture_no_download",
                    "report": report, "approval": decision["decision"],
                    "export_artifact_sha256": exported["artifact"]["artifact_sha256"],
                    "audit_head_hmac": exported["artifact"]["audit_head_hmac"],
                    "negative_checks": checks,
                    "scope": "technical teaching demo, not legal or production approval"}
        path = ROOT / "reports" / "live-observation.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(observed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS ch45 live: n8n -> MCP Resources -> evidence -> human gate -> export")
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
