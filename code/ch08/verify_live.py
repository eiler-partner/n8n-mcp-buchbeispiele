"""Exercise real n8n pagination and the published signed webhook."""

import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from contract import signature


ROOT = Path(__file__).resolve().parent


def compose(*args, capture=False):
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {(result.stdout or '')[-4000:]}")
    return result.stdout or ""


def request(url, raw=None, headers=None):
    call = Request(url, data=raw, headers=headers or {})
    try:
        response = urlopen(call, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response), dict(response.headers)


def workflow_run(workflow_id, final_node):
    output = compose("run", "--rm", "--no-deps", "n8n", "execute", f"--id={workflow_id}", capture=True)
    marker = "Execution was successful:\n====================================\n"
    if marker not in output:
        raise AssertionError(f"Success marker missing: {output[-4000:]}")
    execution, _ = json.JSONDecoder().raw_decode(output.split(marker, 1)[1].lstrip())
    runs = execution["data"]["resultData"]["runData"]
    return [item["json"] for item in runs[final_node][-1]["data"]["main"][0]], runs


def main():
    env = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    api = f"http://127.0.0.1:{env['API_PORT']}"
    webhook = f"http://127.0.0.1:{env['N8N_PORT']}/webhook/ch08-signed-order"
    compose("stop", "n8n")
    try:
        compose("run", "--rm", "--no-deps", "n8n", "import:workflow", "--input=/lab/workflows/ch08-pages.json")
        compose("run", "--rm", "--no-deps", "n8n", "import:workflow", "--input=/lab/workflows/ch08-webhook.json")
        compose("run", "--rm", "--no-deps", "n8n", "publish:workflow", "--id=ch08Webhook")
        compose("up", "-d", "--wait", "n8n")
        compose("stop", "n8n")
        summary, runs = workflow_run("ch08Pages", "Assert Complete Catalog")
        expected = {"page_count": 3, "record_count": 7, "ids": [f"R-{i:03d}" for i in range(1, 8)]}
        if summary != [expected] or len(runs["Fetch Pages"][-1]["data"]["main"][0]) != 3:
            raise AssertionError(f"Pagination output differs: {summary}")
        print("PASS: n8n fetched pages 3 + 3 + 1 and seven distinct IDs")

        compose("up", "-d", "--wait", "n8n")
        status, _, response_headers = request(api + "/throttle")
        if status != 429 or response_headers.get("Retry-After") != "2":
            raise AssertionError("429/Retry-After contract differs")
        baseline = request(api + "/orders/count")[1]["count"]
        suffix = uuid.uuid4().hex[:12]
        event = {"event_id": f"evt-{suffix}", "customer": "Bücher GmbH", "amount_cents": 1250}
        raw = json.dumps(event, ensure_ascii=False, separators=(", ", ": ")).encode("utf-8")
        timestamp = str(int(time.time()))
        delivery = f"del-{suffix}"
        headers = {
            "Content-Type": "application/json",
            "X-Lab-Timestamp": timestamp,
            "X-Lab-Delivery": delivery,
            "X-Lab-Signature": signature(env["WEBHOOK_SECRET"], timestamp, delivery, raw),
            "X-Correlation-ID": f"corr-{suffix}",
        }
        first = request(webhook, raw, headers)
        again = request(webhook, raw, headers)
        if (first[0], first[1].get("duplicate")) != (201, False):
            raise AssertionError(f"First signed delivery failed: {first[:2]}")
        if (again[0], again[1].get("duplicate")) != (200, True):
            raise AssertionError(f"Repeated delivery failed: {again[:2]}")
        print("PASS: signed delivery accepted once, duplicate acknowledged without another order")

        altered = request(webhook, raw + b" ", headers)
        stale_headers = dict(headers)
        stale_headers["X-Lab-Timestamp"] = str(int(timestamp) - 301)
        stale_headers["X-Lab-Signature"] = signature(
            env["WEBHOOK_SECRET"], stale_headers["X-Lab-Timestamp"], delivery, raw
        )
        stale = request(webhook, raw, stale_headers)
        conflicting = {**event, "amount_cents": 2000}
        changed_raw = json.dumps(conflicting, ensure_ascii=False).encode("utf-8")
        conflict_headers = dict(headers)
        conflict_headers["X-Lab-Delivery"] = f"del-other-{suffix}"
        conflict_headers["X-Lab-Signature"] = signature(
            env["WEBHOOK_SECRET"], timestamp, conflict_headers["X-Lab-Delivery"], changed_raw
        )
        conflict = request(webhook, changed_raw, conflict_headers)
        final_count = request(api + "/orders/count")[1]["count"]
        if (altered[0], stale[0], conflict[0], final_count) != (401, 401, 409, baseline + 1):
            raise AssertionError(
                f"Security contract differs: {altered[:2]}, {stale[:2]}, "
                f"{conflict[:2]}, count={final_count}, baseline={baseline}"
            )
        print("PASS: tampering and stale replay rejected; conflicting event rejected; count +1")
    finally:
        compose("up", "-d", "--wait", "n8n")


if __name__ == "__main__":
    main()
