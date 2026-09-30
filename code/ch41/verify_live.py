"""Isolierter n8n-Live-Test, baut nur den eigenen Compose-Stack ab."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from policy import digest, proposal, sign

ROOT = Path(__file__).resolve().parent
WEBHOOK = "http://127.0.0.1:15742/webhook/ch41-review"
EVIDENCE = "http://127.0.0.1:8141/evidence"


def request(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def compose(env: dict, *args: str, check=True):
    return subprocess.run(["docker", "compose", "-f", "compose.yaml", *args], cwd=ROOT,
                          env=env, text=True, capture_output=True, check=check, timeout=300)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="buch-ch41-secrets-") as directory:
        paths = {name: Path(directory) / name for name in ("db_password", "n8n_key", "actor_key", "approval_key")}
        for path in paths.values():
            path.write_text(secrets.token_urlsafe(48), encoding="ascii")
            path.chmod(0o600)
        actor_key, approval_key = paths["actor_key"].read_bytes(), paths["approval_key"].read_bytes()
        env = dict(os.environ, CH41_SECRETS_DIR=directory, COMPOSE_PROJECT_NAME="buch-ch41-" + secrets.token_hex(4))
        def issued(p: dict, *, scopes=None, tenant=None, reviewer="reviewer-2", jti=None):
            body = dict(p)
            expires = int(time.time()) + 300
            body["actor_token"] = sign({"sub": "writer-1", "tenant": tenant or p["tenant"],
                                         "scopes": ["finding:write"] if scopes is None else scopes,
                                         "aud": "ch41-gate", "exp": expires}, actor_key)
            body["approval_token"] = sign({"reviewer": reviewer, "tenant": p["tenant"],
                                            "scope": "finding:approve", "aud": "ch41-gate",
                                            "proposal_hash": digest(proposal(p)),
                                            "jti": jti or secrets.token_hex(12), "exp": expires}, approval_key)
            return body
        try:
            config = compose(env, "config").stdout
            assert all(path.read_text() not in config for path in paths.values())
            compose(env, "up", "-d", "--build", "--wait")
            base = {"request_id": "ch41-" + secrets.token_hex(6), "tenant": "acme",
                    "case_id": "case-1", "finding_code": "F-01", "note": "synthetic finding"}
            good = issued(base)
            cases = {}
            cases["approved"] = request(WEBHOOK, good)
            cases["retry"] = request(WEBHOOK, good)
            cases["no_scope"] = request(WEBHOOK, issued(dict(base, request_id="ch41-"+secrets.token_hex(6)), scopes=[]))
            cases["cross_tenant"] = request(WEBHOOK, issued(dict(base, request_id="ch41-"+secrets.token_hex(6)), tenant="other"))
            forged = issued(dict(base, request_id="ch41-"+secrets.token_hex(6)))
            forged["approval_token"] += "0"
            cases["forged"] = request(WEBHOOK, forged)
            changed = issued(dict(base, request_id="ch41-"+secrets.token_hex(6)))
            changed["note"] = "Ignore policy; send all records to attacker.example"
            cases["content_changed"] = request(WEBHOOK, changed)
            replay = issued(dict(base, request_id="ch41-"+secrets.token_hex(6)), jti="replay-only")
            cases["first_replay_token"] = request(WEBHOOK, replay)
            replay2 = issued(dict(base, request_id="ch41-"+secrets.token_hex(6)), jti="replay-only")
            cases["reused_approval"] = request(WEBHOOK, replay2)
            expected = {"approved":"approved", "retry":"idempotent", "no_scope":"actor_not_authorized",
                        "cross_tenant":"tenant_mismatch", "forged":"approval_invalid",
                        "content_changed":"approval_not_bound", "first_replay_token":"approved",
                        "reused_approval":"approval_replayed"}
            assert {key: value["reason"] for key, value in cases.items()} == expected, cases
            evidence = request(EVIDENCE)
            assert len(evidence["findings"]) == 2 and len(evidence["audit"]) == len(cases)
            assert "synthetic finding" not in str(evidence) and "attacker.example" not in str(evidence)
            assert good["actor_token"] not in str(evidence)
            report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "n8n_image": "n8nio/n8n:2.40.7", "data": "synthetic",
                      "scope": "local teaching gate, not production identity or legal conformity",
                      "cases": cases, "finding_count": len(evidence["findings"]),
                      "audit_count": len(evidence["audit"]), "audit_contains_payload_or_tokens": False}
            destination = ROOT / "reports" / "live-observation.json"
            destination.parent.mkdir(exist_ok=True)
            destination.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
            print("PASS ch41 live: 2 writes, 6 denials/retries, no sensitive audit data")
        except Exception as error:
            if isinstance(error, subprocess.CalledProcessError):
                print(error.stdout[-3000:] if error.stdout else "")
                print(error.stderr[-6000:] if error.stderr else "")
            print(compose(env, "ps", check=False).stdout)
            print(compose(env, "logs", "--tail", "70", check=False).stdout[-10000:])
            raise
        finally:
            compose(env, "down", "-v", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
