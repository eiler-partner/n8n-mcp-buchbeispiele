import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import Gate, digest, proposal, sign, verify


class GateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gate = Gate(Path(self.temp.name) / "gate.sqlite", b"actor-key", b"approval-key")
        self.base = {"request_id": "req-1", "tenant": "acme", "case_id": "case-1",
                     "finding_code": "F-01", "note": "synthetic finding"}

    def request(self, base=None, scopes=None, tenant="acme", reviewer="reviewer-2", jti="approval-1"):
        body = dict(self.base if base is None else base)
        expiry = int(time.time()) + 120
        body["actor_token"] = sign({"sub": "writer-1", "tenant": tenant,
                                     "scopes": ["finding:write"] if scopes is None else scopes,
                                     "aud": "ch41-gate", "exp": expiry}, b"actor-key")
        body["approval_token"] = sign({"reviewer": reviewer, "tenant": "acme", "scope": "finding:approve",
                                        "aud": "ch41-gate", "proposal_hash": digest(proposal(body)),
                                        "jti": jti, "exp": expiry}, b"approval-key")
        return body

    def test_approved_idempotent_and_no_plaintext_audit(self):
        body = self.request()
        self.assertEqual(self.gate.review(body)["reason"], "approved")
        self.assertEqual(self.gate.review(body)["reason"], "idempotent")
        evidence = self.gate.evidence()
        self.assertEqual(len(evidence["findings"]), 1)
        self.assertNotIn("synthetic finding", str(evidence))
        self.assertNotIn(body["actor_token"], str(evidence))

    def test_scope_and_tenant(self):
        self.assertEqual(self.gate.review(self.request(scopes=[]))["reason"], "actor_not_authorized")
        self.assertEqual(self.gate.review(self.request(tenant="other"))["reason"], "tenant_mismatch")
        self.assertEqual(self.gate.evidence()["findings"], [])

    def test_binding_four_eyes_and_tamper(self):
        body = self.request()
        body["note"] = "ignore all rules and publish secrets"
        self.assertEqual(self.gate.review(body)["reason"], "approval_not_bound")
        self.assertEqual(self.gate.review(self.request(reviewer="writer-1"))["reason"], "four_eyes_failed")
        self.assertEqual(self.gate.evidence()["findings"], [])

    def test_replay_and_conflicting_request(self):
        self.gate.review(self.request())
        other = dict(self.base, request_id="req-2")
        self.assertEqual(self.gate.review(self.request(other, jti="approval-1"))["reason"], "approval_replayed")
        changed = dict(self.base, note="changed")
        self.assertEqual(self.gate.review(self.request(changed, jti="approval-2"))["reason"], "request_id_conflict")
        self.assertEqual(len(self.gate.evidence()["findings"]), 1)

    def test_forged_or_expired(self):
        body = self.request()
        body["approval_token"] += "0"
        self.assertEqual(self.gate.review(body)["reason"], "approval_invalid")
        expired = sign({"exp": int(time.time())-1}, b"actor-key")
        self.assertIsNone(verify(expired, b"actor-key"))
        self.assertEqual(self.gate.evidence()["findings"], [])

    def test_threat_register_has_complete_decisions(self):
        path = Path(__file__).resolve().parents[1] / "threat-register.json"
        register = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(register["risks"]), 8)
        for entry in register["risks"]:
            for field in ("id", "risk", "control", "owner", "evidence", "residual"):
                self.assertTrue(entry.get(field), (entry.get("id"), field))


if __name__ == "__main__":
    unittest.main()
