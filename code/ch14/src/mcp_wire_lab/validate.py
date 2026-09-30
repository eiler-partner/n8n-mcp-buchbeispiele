"""Kleine, bewusst transparente Mehr-Ebenen-Prüfung von Wire-Traces.

Die generische Nachricht wird zusätzlich gegen die vom offiziellen Python-SDK
gelieferten Pydantic-Typen geprüft. Reihenfolge und Revisionsregeln brauchen
darüber hinaus zustandsbehaftete Prüfungen.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.types import JSONRPCMessage
from pydantic import TypeAdapter, ValidationError

MESSAGE_SCHEMA = TypeAdapter(JSONRPCMessage)
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
# Parse error und Invalid Request: nur hier darf eine Fehlerantwort ohne
# zuordenbare ID stehen.
UNREADABLE_REQUEST_CODES = {-32700, -32600}


@dataclass(frozen=True)
class Issue:
    layer: str
    frame: int
    code: str
    detail: str


def _issue(layer: str, frame: int, code: str, detail: str) -> Issue:
    return Issue(layer, frame, code, detail)


def _is_id(value: Any) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _header(headers: dict[str, Any], name: str) -> Any:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def validate_trace(trace: dict[str, Any]) -> list[Issue]:
    era = trace.get("era")
    if era not in {"legacy", "modern"}:
        return [_issue("trace", -1, "unknown_era", "era muss legacy oder modern sein")]
    expected_version = "2025-11-25" if era == "legacy" else "2026-07-28"
    frames = trace.get("frames")
    if not isinstance(frames, list):
        return [_issue("trace", -1, "missing_frames", "frames muss eine Liste sein")]
    issues: list[Issue] = []
    pending: dict[str | int, str] = {}
    seen_legacy_ids: set[str | int] = set()
    initialized = False
    init_answered = False

    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            issues.append(_issue("trace", index, "invalid_frame", "Frame muss ein Objekt sein"))
            continue
        direction = frame.get("direction")
        if direction not in {"client->server", "server->client"}:
            issues.append(_issue("trace", index, "invalid_direction", "Richtung fehlt oder ist unbekannt"))
            continue
        message = frame.get("message")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                issues.append(_issue("json", index, "parse_error", "Nachricht ist kein gültiges JSON"))
                continue
        if isinstance(message, list):
            issues.append(_issue("mcp", index, "batch_forbidden", "MCP erwartet ein einzelnes Nachrichtenobjekt"))
            continue
        if not isinstance(message, dict):
            issues.append(_issue("jsonrpc", index, "invalid_request", "Nachricht muss ein Objekt sein"))
            continue
        if message.get("jsonrpc") != "2.0":
            issues.append(_issue("jsonrpc", index, "wrong_jsonrpc", "jsonrpc muss '2.0' sein"))
            continue
        # Fehlerantworten ohne lesbare Anfrage-ID: MCP 2026-07-28 lässt die ID
        # weg, JSON-RPC 2.0 und das Python-SDK verwenden null. Für die
        # SDK-Schemaprüfung wird die fehlende ID deshalb als null ergänzt.
        uncorrelated_error = "error" in message and message.get("id") is None
        schema_view = {**message, "id": None} if uncorrelated_error and "id" not in message else message
        try:
            MESSAGE_SCHEMA.validate_python(schema_view)
        except ValidationError:
            issues.append(_issue("sdk-schema", index, "message_schema", "Offizielles SDK-Nachrichtenmodell lehnt die Form ab"))
        method = message.get("method")
        is_method = method is not None
        if is_method and not isinstance(method, str):
            issues.append(_issue("jsonrpc", index, "invalid_method", "method muss ein String sein"))
            continue
        is_response = not is_method
        has_id = "id" in message
        if isinstance(method, str) and method.startswith("notifications/") and has_id:
            issues.append(_issue("jsonrpc", index, "notification_has_id", "Notification darf keine ID tragen"))
        if is_method and direction != "client->server":
            issues.append(_issue("mcp", index, "wrong_direction", "Dieser Server darf keine Requests initiieren"))
        if is_response and direction != "server->client":
            issues.append(_issue("mcp", index, "wrong_direction", "Client darf keine Responses senden"))

        if is_response:
            if ("result" in message) == ("error" in message):
                issues.append(_issue("jsonrpc", index, "result_xor_error", "Antwort braucht genau result oder error"))
            request_id = message.get("id")
            if uncorrelated_error:
                error = message.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                if code not in UNREADABLE_REQUEST_CODES:
                    issues.append(_issue("jsonrpc", index, "error_without_id", "Fehler ohne ID nur, wenn die Anfrage nicht lesbar war"))
                continue
            if request_id not in pending:
                issues.append(_issue("sequence", index, "unmatched_id", "Keine offene Anfrage mit dieser Antwort-ID"))
            else:
                origin_method = pending.pop(request_id)
                if origin_method == "initialize":
                    init_answered = True
            if era == "modern" and isinstance(message.get("result"), dict):
                if "resultType" not in message["result"]:
                    issues.append(_issue("mcp-modern", index, "missing_result_type", "Modernes Resultat braucht resultType"))
            continue

        if has_id:
            request_id = message["id"]
            if not _is_id(request_id):
                issues.append(_issue("mcp", index, "invalid_id", "MCP-Request-ID muss String oder Integer sein"))
                continue
            if request_id in pending or (era == "legacy" and request_id in seen_legacy_ids):
                issues.append(_issue("sequence", index, "duplicate_id", "Request-ID wird unzulässig erneut benutzt"))
            pending[request_id] = method
            seen_legacy_ids.add(request_id)
        elif method != "notifications/initialized" and era == "legacy":
            # Sonstige Notifications bleiben erlaubt; ihre fachliche Semantik
            # ist nicht Teil des engen Laborvertrags.
            pass

        if era == "legacy":
            if method == "initialize":
                init_params = message.get("params")
                if index != 0 or not isinstance(init_params, dict) or init_params.get("protocolVersion") != expected_version:
                    issues.append(_issue("mcp-legacy", index, "invalid_initialize", "Legacy-Handshake muss zuerst und mit passender Version erfolgen"))
            elif method == "notifications/initialized":
                if not init_answered:
                    issues.append(_issue("sequence", index, "initialized_too_early", "initialized erst nach initialize-Antwort senden"))
                initialized = True
            elif method == "tools/call" and not initialized:
                issues.append(_issue("sequence", index, "call_before_initialized", "Legacy-Toolaufruf vor initialized"))
        elif has_id:
            params = message.get("params")
            meta = params.get("_meta") if isinstance(params, dict) else None
            if not isinstance(meta, dict) or META_VERSION not in meta or META_CAPABILITIES not in meta:
                issues.append(_issue("mcp-modern", index, "missing_meta", "Version und Client-Capabilities fehlen in params._meta"))
            elif meta[META_VERSION] != expected_version:
                issues.append(_issue("mcp-modern", index, "unsupported_version", "Dieser Trace verwendet die falsche Protokollversion"))

        headers = frame.get("headers")
        if headers is not None:
            if not isinstance(headers, dict):
                issues.append(_issue("http", index, "invalid_headers", "headers muss ein Objekt sein"))
            elif era == "modern" and has_id:
                params = message.get("params")
                meta = params.get("_meta", {}) if isinstance(params, dict) else {}
                expected_name = params.get("name", params.get("uri")) if isinstance(params, dict) else None
                mismatch = (
                    _header(headers, "MCP-Protocol-Version") != meta.get(META_VERSION)
                    or _header(headers, "Mcp-Method") != method
                    or (method in {"tools/call", "resources/read", "prompts/get"}
                        and _header(headers, "Mcp-Name") != expected_name)
                )
                if mismatch:
                    issues.append(_issue("http", index, "header_mismatch", "HTTP-Header widersprechen dem JSON-RPC-Body"))

    if pending:
        issues.append(_issue("sequence", len(frames), "unanswered_request", f"Offene Request-IDs: {sorted(map(str, pending))}"))
    if era == "legacy" and not initialized:
        issues.append(_issue("mcp-legacy", len(frames), "missing_initialized", "Legacy-Handshake unvollständig"))
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    issues = validate_trace(trace)
    if issues:
        for issue in issues:
            print(f"FAIL {issue.layer} Frame {issue.frame}: {issue.code} – {issue.detail}")
        raise SystemExit(1)
    print(f"PASS {trace['era']}: {len(trace['frames'])} Frames, keine Vertragsverletzung")


if __name__ == "__main__":
    main()
