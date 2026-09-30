"""Fresh, isolated n8n + MCP integration run; removes only this temporary project."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core import PROTOCOL, corpus, identity, sign, unauthorized_retrieval

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15743/webhook/ch43-ask"
# Golden cases: name -> (question, tenant, groups, expected status). Offline tests reuse this table.
CASES = {
    "staff_travel": ("Wann brauchen Dienstreisen eine Genehmigung?", "acme", ["staff"], "answered"),
    "staff_finance_denied": ("Wie hoch ist das interne Projektbudget Orion 73000?", "acme", ["staff"], "refused"),
    "finance_allowed": ("Wie hoch ist das interne Projektbudget Orion 73000?", "acme", ["finance"], "answered"),
    "cross_tenant_denied": ("Wann schließt der Standort Beta im Dezember?", "acme", ["staff"], "refused"),
    "beta_allowed": ("Wann schließt der Standort Beta im Dezember?", "beta", ["staff"], "answered"),
    # Old wording ("fünf Tage") must still be answered from the current version 2.
    "old_wording_current_version": ("Brauchen Dienstreisen Genehmigung fünf Tage vorher?", "acme", ["staff"], "answered"),
    "ocr_denied": ("Wie hoch ist die Gehaltsanpassung neun Prozent?", "acme", ["staff"], "refused"),
    "absent_refused": ("Welche Marsmission hat die Firma genehmigt?", "acme", ["staff"], "refused"),
}


def compose(env: dict, *args: str, check: bool = True, stdin_text: str | None = None):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args], cwd=ROOT,
                          env=env, text=True, capture_output=True, check=check, timeout=300,
                          input=stdin_text)


def ask(question: str, token: str) -> dict:
    request = urllib.request.Request(WEBHOOK,
        data=json.dumps({"question": question, "actor_token": token}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def mcp_candidates(env: dict, calls: dict[str, tuple[str, str]]) -> dict[str, list[dict]]:
    """Candidate lists before the answer gate: the same MCP program, data and key as the gateway,
    called directly inside the running knowledge container (the webhook reveals no candidates)."""
    lines = [json.dumps({"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": {
        "name": "search_evidence", "arguments": {"question": question, "actor_token": token},
        "_meta": {"io.modelcontextprotocol/protocolVersion": PROTOCOL}}})
        for index, (question, token) in enumerate(calls.values())]
    child = compose(env, "exec", "-T", "knowledge", "python", "mcp_stdio.py",
                    stdin_text="\n".join(lines) + "\n")
    replies = {reply["id"]: reply for reply in
               (json.loads(line) for line in child.stdout.splitlines() if line.strip())}
    assert all("error" not in reply for reply in replies.values()), replies
    return {name: replies[index]["result"]["structuredContent"]["candidates"]
            for index, name in enumerate(calls)}


def main():
    key = secrets.token_urlsafe(48)
    env = dict(os.environ, CH43_SIGNING_KEY=key,
               COMPOSE_PROJECT_NAME="buch-ch43-" + secrets.token_hex(4))
    def token(tenant: str, groups: list[str]) -> str:
        return sign({"sub": "synthetic-reader", "tenant": tenant, "groups": groups,
                     "aud": "ch43-knowledge", "exp": int(time.time()) + 300}, key.encode())
    try:
        compose(env, "up", "-d", "--build", "--wait")
        tokens = {name: token(tenant, groups) for name, (_, tenant, groups, _) in CASES.items()}
        cases = {name: ask(spec[0], tokens[name]) for name, spec in CASES.items()}
        expected = {name: spec[3] for name, spec in CASES.items()}
        actual = {name: case["status"] for name, case in cases.items()}
        assert actual == expected, actual
        assert cases["staff_travel"]["citations"][0]["version"] == 2
        assert "zehn Arbeitstage" in cases["old_wording_current_version"]["answer"]
        assert cases["old_wording_current_version"]["citations"][0]["version"] == 2
        assert all(not case["citations"] for case in cases.values() if case["status"] == "refused")
        assert all(case["citations"] for case in cases.values() if case["status"] == "answered")
        assert all(case["path"] == "n8n-mcp-extractive" for case in cases.values())
        # Unauthorized Retrieval over ALL queries: candidate lists checked against the token's view.
        candidates = mcp_candidates(env, {name: (CASES[name][0], tokens[name]) for name in CASES})
        assert all(len(candidates[name]) == cases[name]["retrieved_count"] for name in CASES), candidates
        leak = unauthorized_retrieval({name: (identity(tokens[name], key.encode()), candidates[name])
                                       for name in CASES})
        assert leak["queries"] == len(CASES), leak
        assert leak["queries_with_forbidden_candidate"] == 0, leak
        chunks, quarantine = corpus()
        report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "n8n_image": "n8nio/n8n:2.40.7", "protocol": "2026-07-28",
                  "data": "synthetic", "model": "extractive_fixture_no_download",
                  "cases": cases, "active_chunks": len(chunks), "quarantine": quarantine,
                  "candidates": {name: [{k: c[k] for k in ("source_id", "version", "section")}
                                        for c in found] for name, found in candidates.items()},
                  "unauthorized_retrieval": dict(leak, definition=(
                      "queries whose candidate list before the answer gate holds at least one chunk "
                      "that is not current, released and readable for the token's tenant and groups "
                      "/ all queries")),
                  "scope": "local teaching demo; not production authentication or semantic embeddings"}
        destination = ROOT / "reports" / "live-observation.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("PASS ch43 live: n8n -> MCP -> authorized retrieval -> checked answer")
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
