"""Kapitel 1: Regeln und Modellantworten an denselben E-Mails prüfen."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CATEGORIES = {"rechnung", "support", "vertrieb", "unsicher"}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(CATEGORIES)},
        "evidence": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["category", "evidence", "reason"],
    "additionalProperties": False,
}
INSTRUCTIONS = (
    "Klassifiziere diese E-Mail als rechnung, support, vertrieb oder unsicher. "
    "Wenn Anliegen gemischt oder die Absicht unklar ist, wähle unsicher. "
    "evidence muss ein wörtlicher Ausschnitt aus Betreff oder Text sein; "
    "bei unsicher darf evidence leer sein. Antworte nur im vorgegebenen Schema."
)


class ModelContractError(ValueError):
    """Ein Provider lieferte keinen auswertbaren Klassifikationsvertrag."""


@dataclass(frozen=True)
class Classification:
    category: str
    evidence: str
    reason: str


def email_text(email: dict[str, str]) -> str:
    return f"{email['subject']}\n{email['body']}"


def rule_classify(email: dict[str, str]) -> Classification:
    text = email_text(email).casefold()
    for category, words in (
        ("rechnung", ("rechnung", "zahlung", "beleg")),
        ("support", ("fehler", "login", "funktioniert", "störung")),
        ("vertrieb", ("angebot", "preis", "lizenz", "demo")),
    ):
        for word in words:
            if word in text:
                return Classification(category, word, f"Regelwort: {word}")
    return Classification("unsicher", "", "Keine Regel passt")


def parse_model_output(raw: str | dict[str, Any], email: dict[str, str]) -> Classification:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ModelContractError("Antwort ist kein JSON") from exc
    if not isinstance(value, dict) or set(value) != {"category", "evidence", "reason"}:
        raise ModelContractError("Felder fehlen oder sind unbekannt")
    if not isinstance(value["category"], str) or value["category"] not in CATEGORIES:
        raise ModelContractError("Kategorie ist unbekannt")
    if not isinstance(value["evidence"], str) or not isinstance(value["reason"], str):
        raise ModelContractError("Beleg oder Begründung ist kein Text")
    evidence = value["evidence"].strip()
    if value["category"] != "unsicher" and not evidence:
        raise ModelContractError("Für eine Zuordnung fehlt der Textbeleg")
    if evidence and evidence.casefold() not in email_text(email).casefold():
        raise ModelContractError("Textbeleg kommt in der E-Mail nicht vor")
    if not value["reason"].strip():
        raise ModelContractError("Begründung fehlt")
    return Classification(value["category"], evidence, value["reason"].strip())


def _post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except json.JSONDecodeError as exc:
        raise ModelContractError("Providerantwort ist kein JSON") from exc
    except (HTTPError, URLError, TimeoutError) as exc:
        # Provider-Fehlerkörper können Eingaben enthalten und werden nicht ausgegeben.
        raise ModelContractError(f"Provideraufruf fehlgeschlagen: {type(exc).__name__}") from exc


def live_classify(provider: str, model: str, email: dict[str, str]) -> Classification:
    if not model:
        raise ModelContractError("Für Live-Aufrufe ist --model erforderlich")
    prompt = email_text(email)
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ModelContractError("OPENAI_API_KEY fehlt")
        response = _post(
            "https://api.openai.com/v1/responses",
            {"model": model, "instructions": INSTRUCTIONS, "input": prompt,
             "text": {"format": {"type": "json_schema", "name": "email_category",
                                 "strict": True, "schema": SCHEMA}}},
            {"Authorization": f"Bearer {key}"},
        )
        if response.get("status") != "completed":
            raise ModelContractError("OpenAI-Antwort ist nicht abgeschlossen")
        blocks = [part.get("text") for item in response.get("output", [])
                  for part in item.get("content", []) if part.get("type") == "output_text"]
        raw = blocks[0] if len(blocks) == 1 else None
    elif provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ModelContractError("ANTHROPIC_API_KEY fehlt")
        response = _post(
            "https://api.anthropic.com/v1/messages",
            {"model": model, "max_tokens": 300, "system": INSTRUCTIONS,
             "messages": [{"role": "user", "content": prompt}],
             "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}},
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        if response.get("stop_reason") != "end_turn":
            raise ModelContractError("Anthropic-Antwort ist nicht abgeschlossen")
        blocks = [part.get("text") for part in response.get("content", [])
                  if part.get("type") == "text"]
        raw = blocks[0] if len(blocks) == 1 else None
    elif provider == "ollama":
        base = os.environ.get("CH01_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        response = _post(
            f"{base}/api/chat",
            {"model": model, "stream": False, "format": SCHEMA,
             "messages": [{"role": "system", "content": INSTRUCTIONS},
                          {"role": "user", "content": prompt}]},
            {},
        )
        raw = response.get("message", {}).get("content")
    else:
        raise ModelContractError(f"Unbekannter Provider: {provider}")
    if not isinstance(raw, str):
        raise ModelContractError("Modell lieferte keinen einzelnen Antworttext")
    return parse_model_output(raw, email)


def evaluate(emails: list[dict[str, str]], provider: str, model: str,
             fixtures: dict[str, dict[str, str]]) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for email in emails:
        try:
            if provider == "rules":
                result = rule_classify(email)
            elif provider == "fixture":
                result = parse_model_output(fixtures[email["id"]], email)
            else:
                result = live_classify(provider, model, email)
            actual, evidence, problem = result.category, result.evidence, ""
        except (KeyError, ModelContractError) as exc:
            actual, evidence, problem = "vertrag_fehler", "", str(exc)
        rows.append({"id": email["id"], "expected": email["expected"],
                     "actual": actual, "evidence": evidence, "problem": problem})
    return {
        "provider": provider,
        "total": len(rows),
        "correct": sum(row["expected"] == row["actual"] for row in rows),
        "wrong": sum(row["actual"] not in {row["expected"], "unsicher", "vertrag_fehler"}
                     for row in rows),
        "review": sum(row["actual"] == "unsicher" for row in rows),
        "contract_errors": sum(row["actual"] == "vertrag_fehler" for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E-Mail-Klassifikation vergleichen")
    parser.add_argument("--provider", choices=("rules", "fixture", "openai", "anthropic", "ollama"),
                        default="fixture")
    parser.add_argument("--model", default=os.environ.get("CH01_MODEL", ""))
    parser.add_argument("--data", type=Path, default=ROOT / "emails.json")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures.json")
    args = parser.parse_args()
    emails = json.loads(args.data.read_text(encoding="utf-8"))
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    print(json.dumps(evaluate(emails, args.provider, args.model, fixtures),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
