"""HTTP-Stufen und lokale Berichte für Kapitel 28."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import CASES, ROOT, ContractError, baseline, compare, review, route, work


def _write_report(path: str, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True})
        elif self.path == "/report":
            self._send(200, compare())
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        routes = {"/baseline": baseline, "/route": route,
                  "/work": work, "/review": review}
        if self.path not in routes:
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ContractError("invalid_body_size")
            payload = json.loads(self.rfile.read(length))
            self._send(200, routes[self.path](payload))
        except (ValueError, UnicodeError):
            self._send(422, {"error": "invalid_json"})
        except ContractError as exc:
            self._send(exc.status, {"error": exc.code})


def _ollama(url: str, data: dict | None = None) -> dict:
    raw = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        url, data=raw, method="POST" if raw is not None else "GET",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def ollama_live(model: str, base_url: str) -> dict:
    tags = _ollama(f"{base_url}/api/tags")
    matches = [item for item in tags["models"] if item["name"] == model]
    if len(matches) != 1 or not matches[0].get("digest"):
        raise RuntimeError("Modell mit vollem Digest nicht lokal installiert")
    schema = {
        "type": "object", "properties": {
            "route": {"type": "string", "enum": ["billing", "privacy", "general"]}
        }, "required": ["route"], "additionalProperties": False,
    }
    observations = []
    for case_id in ("c01", "c03", "c05", "c07"):
        case = CASES[case_id]
        response = _ollama(f"{base_url}/api/generate", {
            "model": model, "stream": False, "think": False,
            "prompt": (
                "Ordne die synthetische Anfrage genau einer Route zu: "
                "billing für Rechnungsauskunft; privacy für Löschung oder "
                "Aufbewahrung; general sonst. Gib nur das JSON-Objekt aus.\n"
                f"Anfrage: {case['text']}"
            ),
            "format": schema, "options": {"temperature": 0, "num_predict": 100},
        })
        try:
            parsed = json.loads(response["response"])
            contract_pass = (type(parsed) is dict and set(parsed) == {"route"}
                             and parsed["route"] in schema["properties"]["route"]["enum"])
            observed_route = parsed.get("route") if contract_pass else None
        except (ValueError, TypeError):
            contract_pass, observed_route = False, None
        observations.append({
            "case_id": case_id, "expected_route": case["expected_route"],
            "observed_route": observed_route, "contract_pass": contract_pass,
            "match_observation": observed_route == case["expected_route"],
            "total_duration_ns": response.get("total_duration"),
        })
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(), "platform": platform.platform(),
        "model": model, "model_digest": matches[0]["digest"],
        "dataset_sha256": compare()["dataset_sha256"],
        "observation_not_benchmark": True, "observations": observations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8128)
    report = sub.add_parser("report")
    report.add_argument("--output", default="reports/comparison.json")
    live = sub.add_parser("ollama-live")
    live.add_argument("--model", default="qwen3:14b")
    live.add_argument("--url", default="http://127.0.0.1:11434")
    live.add_argument("--output", default="reports/ollama-observation.json")
    args = parser.parse_args()
    if args.command == "serve":
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    elif args.command == "report":
        value = compare()
        _write_report(args.output, value)
        print(json.dumps({
            "baseline_pass": value["baseline_pass"], "multi_pass": value["multi_pass"],
            "decision": value["decision"], "output": args.output,
        }, ensure_ascii=False))
    else:
        value = ollama_live(args.model, args.url)
        _write_report(args.output, value)
        print(json.dumps({
            "model": args.model, "contract_pass": sum(
                item["contract_pass"] for item in value["observations"]),
            "route_matches": sum(
                item["match_observation"] for item in value["observations"]),
            "output": args.output,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
