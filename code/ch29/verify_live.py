"""End-to-end-Prüfung zweier unabhängiger n8n-Formulare und der Eskalation."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ch29_lab.store import CASES


ROOT = Path(__file__).resolve().parent
GATE = "http://127.0.0.1:8129"
N8N = "http://127.0.0.1:15729"
STAMP = str(int(time.time()))


def get_json(url: str):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def post_json(url: str, data: dict):
    raw = json.dumps(data, ensure_ascii=False).encode()
    request = Request(url, data=raw, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def wait_state(request_id: str, expected: str, *, timeout=30):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            last = get_json(f"{GATE}/state/{request_id}")
            if last["state"] == expected:
                return last
        except HTTPError as error:
            if error.code != 404:
                raise
        time.sleep(0.2)
    raise AssertionError(f"{request_id}: expected {expected}, got {last}")


def wait_form(url: str, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with urlopen(url, timeout=10) as response:
                if b"<form" in response.read():
                    return
        except HTTPError as error:
            if error.code != 404:
                raise
        time.sleep(0.2)
    raise AssertionError("review form never became ready")


def submit_form(url: str, state: dict, decision: str, actor: str):
    wait_form(url)
    boundary = "----ch29-lab-boundary"
    fields = [state["request_id"], state["proposal_hash"], actor, decision]
    raw = "".join(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"field-{index}\"\r\n\r\n"
        f"{value}\r\n" for index, value in enumerate(fields)
    ).encode() + f"--{boundary}--\r\n".encode()
    request = Request(url, data=raw, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(request, timeout=20) as response:
        assert response.status == 200


def propose(case_id: str, suffix: str):
    request_id = f"ch29-{STAMP}-{suffix}"
    case = CASES[case_id]
    status, result = post_json(f"{N8N}/webhook/ch29-propose", {
        "request_id": request_id, "case_id": case_id,
        "tenant_id": "lab", "draft": case["draft"],
    })
    assert status == 200, result
    assert result["request_id"] == request_id, result
    return wait_state(request_id, "awaiting_owner")


def error_code(url: str, body: dict, status: int, code: str):
    actual, data = post_json(url, body)
    assert (actual, data.get("code")) == (status, code), (actual, data)


def main():
    normal = propose("notice-standard", "normal")
    error_code(f"{GATE}/commit", {"request_id": normal["request_id"],
                                    "tenant_id": "lab", "proposal_hash": normal["proposal_hash"]},
               409, "not_approved")
    assert normal["outbox_count"] == 0
    submit_form(f"{N8N}/form/ch29-owner", normal, "Approve", "alice")
    normal = wait_state(normal["request_id"], "awaiting_reviewer")
    error_code(f"{GATE}/decide", {"request_id": normal["request_id"],
                                    "tenant_id": "lab", "role": "reviewer",
                                    "actor_id": "alice", "decision": "Approve",
                                    "proposal_hash": normal["proposal_hash"]},
               422, "same_actor_forbidden")
    submit_form(f"{N8N}/form/ch29-reviewer", normal, "Approve", "bob")
    normal = wait_state(normal["request_id"], "committed")
    assert normal["outbox_count"] == 1 and normal["tool_calls"] == 1
    status, repeated = post_json(f"{GATE}/commit", {
        "request_id": normal["request_id"], "tenant_id": "lab",
        "proposal_hash": normal["proposal_hash"],
    })
    assert status == 200 and repeated["outbox_count"] == 1 and repeated["tool_calls"] == 1

    denied = propose("notice-deny", "denied")
    submit_form(f"{N8N}/form/ch29-owner", denied, "Deny", "alice")
    denied = wait_state(denied["request_id"], "rejected")
    assert denied["outbox_count"] == 0

    timed = propose("notice-timeout", "timed")
    submit_form(f"{N8N}/form/ch29-owner", timed, "Approve", "alice")
    timed = wait_state(timed["request_id"], "awaiting_reviewer")
    time.sleep(1.2)
    status, escalated = post_json(f"{N8N}/webhook/ch29-escalate", {
        "request_id": timed["request_id"], "tenant_id": "lab",
        "role": "escalation", "actor_id": "carol", "decision": "Approve",
        "proposal_hash": timed["proposal_hash"],
    })
    assert status == 200 and escalated["state"] == "committed", (status, escalated)
    timed = wait_state(timed["request_id"], "committed")
    assert timed["outbox_count"] == 1
    assert "review_timeout_escalated" in [row["event"] for row in timed["audit"]]

    error_code(f"{GATE}/propose", {
        "request_id": f"ch29-{STAMP}-tamper", "case_id": "notice-standard",
        "tenant_id": "lab", "draft": CASES["notice-standard"]["draft"] + " erfunden",
    }, 422, "draft_guardrail")

    result = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_data_only": True,
        "n8n_owner_and_reviewer_forms": True,
        "n8n_escalation_webhook": True,
        "identity_authenticated": False,
        "cases": [{"request_id": item["request_id"], "state": item["state"],
                   "outbox_count": item["outbox_count"], "tool_calls": item["tool_calls"],
                   "events": [row["event"] for row in item["audit"]]}
                  for item in (normal, denied, timed)],
        "negative_checks": ["preapproval_write_blocked", "same_actor_blocked",
                            "duplicate_commit_idempotent", "tampered_draft_blocked"],
    }
    path = ROOT / "reports/live-observation.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("PASS: two forms, denial, timeout escalation, one-write contract")
    print(path)


if __name__ == "__main__":
    main()
