from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import platform
import urllib.request

from .contracts import (CORE_FIELDS, full_report, grade_case,
                        load_registry, sha256_json, validate_output)


class Handler(BaseHTTPRequestHandler):
    def _respond(self, status: int, payload: dict) -> None:
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        elif self.path == "/report":
            self._respond(200, full_report())
        else:
            self._respond(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/extract":
            self._respond(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 4096:
                raise ValueError("Ungültige Request-Größe")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"case_id", "variant"}:
                raise ValueError("case_id und variant sind erforderlich")
            schema, cases, fixtures, _ = load_registry()
            case = next((item for item in cases if item["id"] == payload["case_id"]), None)
            if case is None or payload["variant"] not in fixtures:
                raise ValueError("Unbekannter Fall oder Variante")
            result = grade_case(case, fixtures[payload["variant"]][case["id"]], schema)
            result["variant"] = payload["variant"]
            self._respond(200, result)
        except (ValueError, TypeError, KeyError) as exc:
            self._respond(422, {"error": str(exc)})


def ollama_live(base_url: str, model: str) -> dict:
    schema, cases, _, prompts = load_registry()

    def fetch(path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)

    matching = [item for item in fetch("/api/tags")["models"]
                if model in (item.get("name"), item.get("model"))]
    if len(matching) != 1 or not matching[0].get("digest"):
        raise ValueError("Modell und vollständiger Digest fehlen in /api/tags")
    observations = []
    for case in [item for item in cases if item["id"] in {"c01", "c02", "c03"}]:
        answer = fetch("/api/generate", {
            "model": model, "system": prompts["v2"], "prompt": case["text"],
            "format": schema, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": 180},
        })
        validation = validate_output(
            answer.get("response", ""), case["text"], schema,
            truncated=answer.get("done") is not True or answer.get("done_reason") == "length",
        )
        observations.append({
            "case_id": case["id"], "contract_pass": validation["contract_pass"],
            "error_class": validation["error_class"],
            "golden_match_observation": validation["value"] == case["golden"] if validation["contract_pass"] else False,
            "core_fields_match_observation": all(
                validation["value"][key] == case["golden"][key]
                for key in CORE_FIELDS
            ) if validation["contract_pass"] else False,
            "response": answer.get("response"), "total_duration_ns": answer.get("total_duration"),
            "prompt_eval_count": answer.get("prompt_eval_count"), "eval_count": answer.get("eval_count"),
        })
    return {
        "observation_not_benchmark": True,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(), "platform": platform.platform(),
        "ollama_version": fetch("/api/version").get("version"),
        "model": model, "model_digest": matching[0]["digest"],
        "prompt_version": "v2",
        "prompt_sha256": hashlib.sha256(prompts["v2"].encode("utf-8")).hexdigest(),
        "schema_sha256": sha256_json(schema), "dataset_sha256": sha256_json(cases),
        "generation_options": {"stream": False, "think": False, "temperature": 0, "num_predict": 180},
        "observations": observations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kapitel-26-Prompt- und Schema-Labor")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("report")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8126)
    live = commands.add_parser("ollama-live")
    live.add_argument("--model", default="qwen3:14b")
    live.add_argument("--base-url", default="http://127.0.0.1:11434")
    live.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        print(json.dumps(full_report(), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    else:
        report = ollama_live(args.base_url, args.model)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
        else:
            print(serialized, end="")
        if any(not item["contract_pass"] for item in report["observations"]):
            raise SystemExit("Mindestens ein Live-Vertrag wurde verletzt; Bericht wurde gespeichert")


if __name__ == "__main__":
    main()
