from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import urllib.request

from .selection import SelectionError, dataset_digest, evaluate, fallback, full_report, load_data


def choose(scenario: str, failure_kind: str | None = None, case_id: str | None = None) -> dict:
    cases, profiles, scenarios = load_data()
    report = evaluate(scenario, cases, profiles, scenarios)
    if report["selected"] is None:
        raise SelectionError("Kein zulässiges Profil vorhanden")
    if failure_kind is not None:
        report["fallback_from"] = report["selected"]
        report["selected"] = fallback(report, report["selected"], failure_kind)
        report["fallback_reason"] = failure_kind
    if case_id is not None:
        case = next((item for item in cases if item["id"] == case_id), None)
        if case is None or case["task"] != scenarios[scenario]["task"]:
            raise SelectionError("Testfall passt nicht zum Szenario")
        profile = next(item for item in profiles if item["id"] == report["selected"])
        report["fixture_invocation"] = {
            "case_id": case_id, "profile": report["selected"],
            "observed": profile["outputs"][case_id], "expected": case["expected"],
            "is_synthetic": True,
        }
    return report


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.path == "/report":
            self._json(200, full_report())
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/choose":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise SelectionError("Ungültige Request-Größe")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) - {"scenario", "failure_kind", "case_id"}:
                raise SelectionError("Ungültiger Request-Vertrag")
            if not isinstance(payload.get("scenario"), str):
                raise SelectionError("Szenario fehlt")
            failure = payload.get("failure_kind")
            if failure is not None and not isinstance(failure, str):
                raise SelectionError("Ungültiger Fehlertyp")
            case_id = payload.get("case_id")
            if case_id is not None and not isinstance(case_id, str):
                raise SelectionError("Ungültiger Testfall")
            self._json(200, choose(payload["scenario"], failure, case_id))
        except (SelectionError, ValueError, TypeError) as exc:
            self._json(422, {"error": str(exc)})


def ollama_live(base_url: str, model: str) -> dict:
    def get_json(path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)

    cases, _, _ = load_data()
    matching = [item for item in get_json("/api/tags")["models"] if model in (item.get("name"), item.get("model"))]
    if len(matching) != 1 or not matching[0].get("digest"):
        raise SelectionError("Modellname oder vollständiger Digest fehlen in Ollama /api/tags")
    observed = []
    for case in [item for item in cases if item["id"] in {"c01", "c02", "e01"}]:
        prompt = (
            "Ordne den folgenden synthetischen Text genau einer Klasse zu: "
            "rechnung oder hinweis. Antworte mit genau einem Wort in Kleinbuchstaben, "
            "ohne Erklärung.\nText: " + case["text"]
        )
        result = get_json("/api/generate", {
            "model": model, "prompt": prompt, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": 24},
        })
        answer = result.get("response", "").strip().lower()
        if result.get("done") is not True or answer not in {"rechnung", "hinweis"}:
            raise SelectionError(f"Live-Vertrag für {case['id']} verletzt: {answer!r}")
        observed.append({
            "case_id": case["id"], "expected": case["expected"], "observed": answer,
            "correct_observation": answer == case["expected"],
            "total_duration_ns": result.get("total_duration"),
            "prompt_eval_count": result.get("prompt_eval_count"),
            "eval_count": result.get("eval_count"),
        })
    return {
        "observation_not_benchmark": True,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(), "platform": platform.platform(),
        "ollama_version": get_json("/api/version").get("version"),
        "model": model, "model_digest": matching[0]["digest"],
        "dataset_sha256": dataset_digest(cases), "prompt_version": "ch25-classify-v1",
        "generation_options": {"stream": False, "think": False, "temperature": 0, "num_predict": 24},
        "observations": observed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministisches Kapitel-25-Auswahllabor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("report")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8125)
    live = sub.add_parser("ollama-live")
    live.add_argument("--base-url", default="http://127.0.0.1:11434")
    live.add_argument("--model", default="qwen3:14b")
    live.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        print(json.dumps(full_report(), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    else:
        report = ollama_live(args.base_url, args.model)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")


if __name__ == "__main__":
    main()
