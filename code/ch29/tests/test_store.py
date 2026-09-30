from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ch29_lab.store import CASES, PolicyError, Store


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.time = 1_800_000_000.0
        self.store = Store(Path(self.temp.name) / "store.sqlite3", clock=lambda: self.time)

    def propose(self, case_id="notice-standard", request_id="case-0001"):
        case = CASES[case_id]
        return self.store.propose({"request_id": request_id, "case_id": case_id,
                                   "tenant_id": "lab", "draft": case["draft"]})

    def decide(self, state, role, actor, decision="Approve", digest=None):
        return self.store.decide({"request_id": state["request_id"], "tenant_id": "lab",
                                  "role": role, "actor_id": actor, "decision": decision,
                                  "proposal_hash": digest or state["proposal_hash"]})

    def commit(self, state):
        return self.store.commit({"request_id": state["request_id"], "tenant_id": "lab",
                                  "proposal_hash": state["proposal_hash"]})

    def assert_error(self, code, fn, *args, **kwargs):
        with self.assertRaises(PolicyError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_two_distinct_approvals_then_one_write(self):
        state = self.propose()
        self.assert_error("not_approved", self.commit, state)
        state = self.decide(state, "owner", "alice")
        self.assert_error("not_approved", self.commit, state)
        state = self.decide(state, "reviewer", "bob")
        state = self.commit(state)
        self.assertEqual((state["state"], state["outbox_count"], state["tool_calls"]),
                         ("committed", 1, 1))
        self.assertEqual(self.commit(state)["outbox_count"], 1)
        self.assertEqual([e["event"] for e in self.store.state("case-0001")["audit"]],
                         ["proposed", "owner_approved", "reviewer_approved", "outbox_written"])

    def test_owner_deny_blocks_write(self):
        state = self.decide(self.propose(), "owner", "alice", "Deny")
        self.assertEqual(state["state"], "rejected")
        self.assert_error("not_approved", self.commit, state)
        self.assertEqual(self.store.state("case-0001")["outbox_count"], 0)

    def test_reviewer_deny_blocks_write(self):
        state = self.decide(self.propose(), "owner", "alice")
        state = self.decide(state, "reviewer", "bob", "Deny")
        self.assert_error("not_approved", self.commit, state)

    def test_same_actor_cannot_review(self):
        state = self.decide(self.propose(), "owner", "alice")
        self.assert_error("same_actor_forbidden", self.decide, state, "reviewer", "alice")
        self.assertEqual(self.store.state("case-0001")["state"], "awaiting_reviewer")

    def test_reviewer_cannot_go_first(self):
        self.assert_error("wrong_stage", self.decide, self.propose(), "reviewer", "bob")

    def test_escalation_after_reviewer_timeout_preserves_two_eyes(self):
        state = self.decide(self.propose("notice-timeout"), "owner", "alice")
        self.time += 2
        state = self.store.tick({"request_id": state["request_id"], "tenant_id": "lab"})
        self.assertEqual(state["state"], "escalated")
        self.assert_error("not_approved", self.commit, state)
        self.assert_error("same_actor_forbidden", self.decide, state, "escalation", "alice")
        self.assert_error("wrong_stage", self.decide, state, "reviewer", "bob")
        state = self.decide(state, "escalation", "carol")
        self.assertEqual(self.commit(state)["outbox_count"], 1)

    def test_late_reviewer_persists_escalation(self):
        state = self.decide(self.propose("notice-timeout"), "owner", "alice")
        self.time += 2
        self.assert_error("wrong_stage", self.decide, state, "reviewer", "bob")
        self.assertEqual(self.store.state("case-0001")["state"], "escalated")

    def test_escalation_deny_blocks_write(self):
        state = self.decide(self.propose("notice-timeout"), "owner", "alice")
        self.time += 2
        state = self.store.tick({"request_id": state["request_id"], "tenant_id": "lab"})
        state = self.decide(state, "escalation", "carol", "Deny")
        self.assert_error("not_approved", self.commit, state)

    def test_owner_timeout_cannot_be_escalated_around(self):
        state = self.propose()
        self.time += 121
        state = self.store.tick({"request_id": state["request_id"], "tenant_id": "lab"})
        self.assertEqual(state["state"], "expired")
        self.assert_error("wrong_stage", self.decide, state, "escalation", "carol")

    def test_escalation_timeout_is_terminal(self):
        state = self.decide(self.propose("notice-timeout"), "owner", "alice")
        self.time += 2
        self.store.tick({"request_id": state["request_id"], "tenant_id": "lab"})
        self.time += 61
        state = self.store.tick({"request_id": state["request_id"], "tenant_id": "lab"})
        self.assertEqual(state["state"], "expired")
        self.assert_error("not_approved", self.commit, state)

    def test_ready_timeout_is_terminal(self):
        state = self.decide(self.decide(self.propose(), "owner", "alice"),
                            "reviewer", "bob")
        self.time += 61
        self.assert_error("not_approved", self.commit, state)
        self.assertEqual(self.store.state("case-0001")["state"], "expired")
        self.assertEqual(self.store.state("case-0001")["outbox_count"], 0)

    def test_tampered_hash_blocks_decision(self):
        self.assert_error("proposal_changed", self.decide, self.propose(),
                          "owner", "alice", digest="0" * 64)

    def test_tampered_draft_blocks_proposal(self):
        case = CASES["notice-standard"]
        self.assert_error("draft_guardrail", self.store.propose,
                          {"request_id": "case-0001", "case_id": "notice-standard",
                           "tenant_id": "lab", "draft": case["draft"] + " ERFUNDEN"})

    def test_request_id_conflict(self):
        self.propose()
        self.assert_error("request_id_conflict", self.propose, "notice-deny")

    def test_tenant_mismatch(self):
        state = self.propose()
        self.assert_error("tenant_mismatch", self.store.commit,
                          {"request_id": state["request_id"], "tenant_id": "other",
                           "proposal_hash": state["proposal_hash"]})

    def test_actor_shape_invalid(self):
        self.assert_error("actor_invalid", self.decide, self.propose(), "owner", "x")


if __name__ == "__main__":
    unittest.main()
