from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mcp_wire_lab.capture import capture
from mcp_wire_lab.validate import validate_trace

ROOT = Path(__file__).resolve().parents[1]


def load(era: str) -> dict:
    return json.loads((ROOT / "traces" / f"{era}.json").read_text(encoding="utf-8"))


def codes(trace: dict) -> set[str]:
    return {item.code for item in validate_trace(trace)}


@pytest.mark.parametrize("era", ["legacy", "modern"])
def test_saved_trace_is_valid(era: str) -> None:
    assert validate_trace(load(era)) == []


@pytest.mark.parametrize("era", ["legacy", "modern"])
def test_live_sdk_capture_is_valid(era: str) -> None:
    fresh = capture(era)
    assert validate_trace(fresh) == []
    assert fresh == load(era)


def test_modern_and_legacy_return_same_business_result() -> None:
    legacy = load("legacy")["frames"][-1]["message"]["result"]["structuredContent"]
    modern = load("modern")["frames"][-1]["message"]["result"]["structuredContent"]
    assert legacy == modern == {
        "document_id": "DOC-101", "title": "Reiserichtlinie", "status": "approved"
    }


def test_invalid_json_is_a_parse_error() -> None:
    trace = load("modern")
    trace["frames"][2]["message"] = '{"jsonrpc": "2.0",'
    assert "parse_error" in codes(trace)


def test_wrong_jsonrpc_version() -> None:
    trace = load("modern")
    trace["frames"][2]["message"]["jsonrpc"] = "1.0"
    assert "wrong_jsonrpc" in codes(trace)


def test_response_id_must_match() -> None:
    trace = load("modern")
    trace["frames"][3]["message"]["id"] = "other"
    assert "unmatched_id" in codes(trace)


def test_notification_must_not_have_id() -> None:
    trace = load("legacy")
    trace["frames"][2]["message"]["id"] = "wrong"
    assert "notification_has_id" in codes(trace)


def test_mcp_does_not_accept_jsonrpc_batch() -> None:
    trace = load("modern")
    trace["frames"][2]["message"] = [trace["frames"][2]["message"]]
    assert "batch_forbidden" in codes(trace)


def test_modern_request_needs_meta() -> None:
    trace = load("modern")
    del trace["frames"][2]["message"]["params"]["_meta"]
    assert "missing_meta" in codes(trace)


def test_modern_result_needs_result_type() -> None:
    trace = load("modern")
    del trace["frames"][3]["message"]["result"]["resultType"]
    assert "missing_result_type" in codes(trace)


def test_modern_version_is_checked() -> None:
    trace = load("modern")
    meta = trace["frames"][2]["message"]["params"]["_meta"]
    meta["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    assert "unsupported_version" in codes(trace)


def test_modern_http_headers_must_match_body() -> None:
    trace = load("modern")
    trace["frames"][2]["headers"] = {
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": "tools/call",
        "Mcp-Name": "wrong_tool",
    }
    assert "header_mismatch" in codes(trace)
    trace["frames"][2]["headers"]["Mcp-Name"] = "read_policy"
    assert validate_trace(trace) == []


def test_legacy_call_before_initialized_is_detected() -> None:
    trace = load("legacy")
    trace["frames"].pop(2)
    assert "call_before_initialized" in codes(trace)


def test_modern_null_id_is_not_mcp_request() -> None:
    trace = load("modern")
    trace["frames"][2]["message"]["id"] = None
    assert "invalid_id" in codes(trace)


def test_request_id_reuse_only_after_result_in_modern_era() -> None:
    trace = load("modern")
    again = copy.deepcopy(trace["frames"][2:])
    trace["frames"].extend(again)
    assert validate_trace(trace) == []
    trace["era"] = "legacy"
    assert "duplicate_id" in codes(trace)


@pytest.mark.parametrize("id_form", ["absent", "null"])
def test_error_for_unreadable_request_needs_no_matching_id(id_form: str) -> None:
    """MCP 2026-07-28 lässt die ID weg, JSON-RPC 2.0 und das SDK senden null."""
    trace = load("modern")
    error = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
    if id_form == "null":
        error["id"] = None
    trace["frames"].append({"direction": "server->client", "message": error})
    assert validate_trace(trace) == []


def test_error_without_id_is_only_allowed_for_unreadable_requests() -> None:
    trace = load("modern")
    trace["frames"].append({
        "direction": "server->client",
        "message": {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params"}},
    })
    assert "error_without_id" in codes(trace)


def load_appendix() -> dict:
    return json.loads((ROOT / "traces" / "appendix-c-modern.json").read_text(encoding="utf-8"))


def test_appendix_c_trace_is_valid() -> None:
    """Das gekürzte Trace aus Anhang C hält den Wire-Vertrag ein."""
    assert validate_trace(load_appendix()) == []


def test_appendix_c_mrtr_retry_contract() -> None:
    frames = load_appendix()["frames"]
    first, interim, retry = (frames[i]["message"] for i in (2, 3, 4))
    assert interim["result"]["resultType"] == "input_required"
    assert retry["id"] != first["id"]
    assert retry["params"]["arguments"] == first["params"]["arguments"]
    assert retry["params"]["requestState"] == interim["result"]["requestState"]
    assert set(retry["params"]["inputResponses"]) == set(interim["result"]["inputRequests"])


def test_appendix_c_header_mismatch_is_detected() -> None:
    trace = copy.deepcopy(load_appendix())
    trace["frames"][2]["headers"]["Mcp-Name"] = "delete_policy"
    assert "header_mismatch" in codes(trace)
