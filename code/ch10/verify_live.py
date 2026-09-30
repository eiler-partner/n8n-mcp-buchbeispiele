"""Exercise recovery paths through published local n8n workflows."""

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
ENV = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)
WEBHOOK = f"http://127.0.0.1:{ENV['N8N_PORT']}/webhook/ch10-document"
SERVICE = f"http://127.0.0.1:{ENV['LAB_PORT']}"


def compose(*args):
    result = subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)}: {(result.stdout + result.stderr)[-3000:]}")


def get(path):
    with urlopen(SERVICE + path, timeout=10) as response:
        return json.load(response)


def submit(scenario):
    doc_id = "L-" + uuid.uuid4().hex[:12]
    data = json.dumps(
        {"doc_id": doc_id, "content": "Synthetisches Dokument ohne Personendaten", "scenario": scenario}
    ).encode()
    with urlopen(Request(WEBHOOK, data=data, headers={"Content-Type": "application/json"}), timeout=10) as response:
        assert response.status == 200
    return doc_id


def wait_state(doc_id, expected, *, timeout=18):
    deadline = time.monotonic() + timeout
    state = None
    while time.monotonic() < deadline:
        try:
            state = get("/state/" + doc_id)
        except HTTPError as error:
            if error.code != 404:
                raise
            time.sleep(0.25)
            continue
        if state["state"] == expected:
            return state
        time.sleep(0.25)
    raise AssertionError(f"{doc_id}: expected {expected}, got {state}")


def wait_form(url, *, timeout=18):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=10) as response:
                if b"<form" in response.read():
                    return
        except HTTPError as error:
            if error.code != 404:
                raise
        time.sleep(0.25)
    raise AssertionError("approval form was not ready before n8n restart")


def decide(state, choice):
    url = state["approval_url"]
    assert url and b"<form" in urlopen(url, timeout=10).read()
    boundary = "----ch10-lab-boundary"
    raw = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"field-0\"\r\n\r\n"
        f"{choice}\r\n--{boundary}--\r\n"
    ).encode()
    request = Request(url, data=raw, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(request, timeout=20) as response:
        assert response.status == 200


def prepare():
    compose("stop", "n8n")
    try:
        for name in ("error", "main"):
            compose("run", "--rm", "--no-deps", "n8n", "import:workflow", f"--input=/lab/workflows/ch10-{name}.json")
        for workflow_id in ("ch10Error", "ch10Main"):
            compose("run", "--rm", "--no-deps", "n8n", "publish:workflow", f"--id={workflow_id}")
    finally:
        compose("up", "-d", "--wait", "n8n")


def main():
    if "--prepare" in sys.argv:
        prepare()
    baseline = get("/alerts/count")["count"]
    permanent = wait_state(submit("permanent"), "quarantined")
    assert (permanent["attempts"], permanent["reason"]) == (1, "schema_invalid")
    print("PASS permanent 422: one attempt, quarantine")

    exhausted = wait_state(submit("always_transient"), "quarantined")
    assert (exhausted["attempts"], exhausted["reason"]) == (3, "retry_exhausted")
    print("PASS repeated 503: three attempts, quarantine")

    transient = wait_state(submit("transient"), "awaiting_approval")
    assert transient["attempts"] == 2
    decide(transient, "Approve")
    assert wait_state(transient["doc_id"], "published")["publish_count"] == 1
    print("PASS transient 503: retry, approval, one publication")

    denied = wait_state(submit("clean"), "awaiting_approval")
    decide(denied, "Deny")
    denied = wait_state(denied["doc_id"], "denied")
    assert denied["publish_count"] == 0
    print("PASS human denial: no publication")

    restarting = wait_state(submit("clean"), "awaiting_approval")
    approval_url = restarting["approval_url"]
    assert approval_url
    wait_form(approval_url)
    compose("restart", "n8n")
    compose("up", "-d", "--wait", "n8n")
    still_waiting = wait_state(restarting["doc_id"], "awaiting_approval")
    assert still_waiting["approval_url"] == approval_url
    decide(still_waiting, "Approve")
    after_restart = wait_state(restarting["doc_id"], "published")
    assert (after_restart["attempts"], after_restart["publish_count"]) == (1, 1)
    print("PASS n8n restart while waiting: same approval resumes, one publication")

    timeout = wait_state(submit("timeout_after_commit"), "awaiting_approval")
    decide(timeout, "Approve")
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline:
        result = get("/state/" + timeout["doc_id"])
        if result["publish_attempts"] >= 2:
            break
        time.sleep(0.25)
    assert (result["state"], result["publish_attempts"], result["publish_count"]) == (
        "published", 2, 1
    ), result
    print("PASS timeout after commit: two calls, one durable publication")

    unexpected = submit("unexpected")
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline and get("/alerts/count")["count"] < baseline + 1:
        time.sleep(0.25)
    assert get("/alerts/count")["count"] == baseline + 1
    assert get("/state/" + unexpected)["attempts"] == 1
    print("PASS unexpected 500: central error workflow records one alert")

    submit("not_a_scenario")
    deadline = time.monotonic() + 18
    while time.monotonic() < deadline and get("/alerts/count")["count"] < baseline + 2:
        time.sleep(0.25)
    assert get("/alerts/count")["count"] == baseline + 2
    print("PASS invalid envelope 400: rejected and centrally alerted")


if __name__ == "__main__":
    main()
