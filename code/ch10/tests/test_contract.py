import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contract import Store


@pytest.fixture
def store():
    with TemporaryDirectory() as directory:
        yield Store(Path(directory) / "lab.sqlite3")


def document(doc_id="D-1", scenario="clean", content="Synthetic document"):
    return {"doc_id": doc_id, "content": content, "scenario": scenario}


def test_transient_then_prepared(store):
    assert store.analyze(document(scenario="transient"))[0] == 503
    assert store.analyze(document(scenario="transient")) == (
        200, {"code": "prepared", "doc_id": "D-1", "attempt": 2}
    )
    assert store.state("D-1")["attempts"] == 2


def test_permanent_fails_without_retry_and_can_quarantine(store):
    assert store.analyze(document(scenario="permanent"))[0] == 422
    assert store.quarantine("D-1", "schema_invalid")[0] == 200
    assert store.state("D-1")["state"] == "quarantined"
    assert store.state("D-1")["attempts"] == 1


def test_retries_are_bounded_by_caller_and_quarantined(store):
    for _ in range(3):
        assert store.analyze(document(scenario="always_transient"))[0] == 503
    store.quarantine("D-1", "retry_exhausted")
    assert store.state("D-1")["attempts"] == 3
    assert store.state("D-1")["state"] == "quarantined"


def test_idempotent_publish_after_lost_response(store):
    store.analyze(document(scenario="timeout_after_commit"))
    store.approval_link("D-1", "http://127.0.0.1:15684/form-waiting/token")
    store.approve("D-1")
    first = store.publish("D-1")
    second = store.publish("D-1")
    assert first == (201, {"doc_id": "D-1", "state": "published", "duplicate": False}, True)
    assert second == (200, {"doc_id": "D-1", "state": "published", "duplicate": True}, False)
    assert store.state("D-1")["publish_count"] == 1
    assert store.state("D-1")["publish_attempts"] == 2


def test_changed_intent_same_id_is_conflict(store):
    store.analyze(document())
    assert store.analyze(document(content="Changed"))[0] == 409
    assert store.state("D-1")["attempts"] == 1


def test_denial_blocks_publication(store):
    store.analyze(document())
    store.approval_link("D-1", "http://127.0.0.1:15684/form-waiting/token")
    assert store.deny("D-1")[0] == 200
    assert store.publish("D-1")[0] == 409
    assert store.state("D-1")["publish_count"] == 0


def test_approval_link_only_for_prepared_document(store):
    url = "http://127.0.0.1:15684/form-waiting/token"
    assert store.approval_link("D-1", url)[0] == 409
    store.analyze(document())
    assert store.approval_link("D-1", url)[0] == 200
    assert store.state("D-1")["approval_url"] == url


def test_publish_requires_recorded_approval(store):
    store.analyze(document())
    assert store.publish("D-1")[0] == 409
    store.approval_link("D-1", "http://127.0.0.1:15684/form-waiting/token")
    assert store.publish("D-1")[0] == 409
    assert store.approve("D-1")[0] == 200
    assert store.publish("D-1")[0] == 201


def test_unexpected_failure_is_not_a_retryable_status(store):
    assert store.analyze(document(scenario="unexpected"))[0] == 500
    assert store.state("D-1")["attempts"] == 1


def test_alert_idempotency(store):
    store.alert("wf", "ex", "failure")
    store.alert("wf", "ex", "failure")
    assert store.alert_count() == 1
