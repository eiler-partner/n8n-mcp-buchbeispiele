"""Transparente, deterministische Lehrentscheidung; keine Beschaffungsautomatik."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRITERIA = ("operability", "data_control", "model_access", "portability", "cost_predictability")
CAPABILITIES = {
    "cloud": {"operability": 5, "data_control": 1, "model_access": 5, "portability": 2, "cost_predictability": 2},
    "self_hosted": {"operability": 2, "data_control": 5, "model_access": 3, "portability": 4, "cost_predictability": 3},
    "hybrid": {"operability": 1, "data_control": 4, "model_access": 5, "portability": 3, "cost_predictability": 2},
}
POLICY_VERSION = "ch37-teaching-policy-v1"
ORDER = tuple(CAPABILITIES)

IMPACTS = {
    "cloud": {
        "trust_boundary": "Client -> n8n Cloud -> freigegebene Daten-/Modell-APIs",
        "spof": ["Cloud-Kontrollpfad", "Identitaetsanbieter", "externe Modell-API"],
        "cost_drivers": ["Plangebuehr/Ausfuehrungen", "Modell-Tokens", "Daten- und Egress-Gebuehren"],
        "raci": {"workflow_owner": "Kunde", "n8n_runtime": "n8n", "data_classification": "Kunde", "model_endpoint": "API-Anbieter"},
        "exit": ["Workflowexport und Credential-Inventar", "Daten-/Logexport und Loeschbestaetigung", "MCP-/API-Endpunkte umstellen", "Vergleichstest und Rueckfallplan"],
    },
    "self_hosted": {
        "trust_boundary": "Client -> eigenes n8n -> eigene Daten/MCP -> lokales Modell",
        "spof": ["Main-Instanz ohne Multi-Main", "PostgreSQL", "Redis bei Queue Mode", "lokaler Modellhost"],
        "cost_drivers": ["Compute/Storage", "Betrieb und Bereitschaft", "Backup/Restore", "eventuelle Edition"],
        "raci": {"workflow_owner": "Kunde", "n8n_runtime": "Kunde", "data_classification": "Kunde", "model_endpoint": "Kunde"},
        "exit": ["Workflow-/Daten-/Credential-Inventar", "verschluesselte Backups samt Schluessel", "lokales Modell-/Indexformat exportieren", "Restore-Probe und DNS-Umschaltung"],
    },
    "hybrid": {
        "trust_boundary": "Client -> eigenes n8n/MCP/Index -> Egress-Gate -> externe Modell-API",
        "spof": ["Egress-Gate", "eigene Datenbank/Index", "externe Modell-API", "Identitaetsanbieter"],
        "cost_drivers": ["eigener Betrieb", "Modell-Tokens", "Egress", "Netz-/Sicherheitskontrolle"],
        "raci": {"workflow_owner": "Kunde", "n8n_runtime": "Kunde", "data_classification": "Kunde", "model_endpoint": "API-Anbieter"},
        "exit": ["Prompt-/Tool-Datenfluesse inventarisieren", "lokales Modell als Rueckfall testen", "Provider-Endpunkte und Tokens tauschen", "Drittanbieter-Datenloeschung pruefen"],
    },
}


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate(profile: dict) -> None:
    expected = {"id", "label", "data_policy", "ops_team", "private_retrieval",
                "external_model_approved", "requires_multi_main", "community_only",
                "third_party_hosting", "weights"}
    if not isinstance(profile, dict) or set(profile) != expected:
        raise ValueError("invalid_profile_fields")
    if not isinstance(profile["id"], str) or not profile["id"] or len(profile["id"]) > 80:
        raise ValueError("invalid_id")
    if not isinstance(profile["label"], str) or not profile["label"] or len(profile["label"]) > 160:
        raise ValueError("invalid_label")
    if profile["data_policy"] not in ("local_only", "split_allowed", "external_allowed"):
        raise ValueError("invalid_data_policy")
    for key in ("ops_team", "private_retrieval", "external_model_approved",
                "requires_multi_main", "community_only", "third_party_hosting"):
        if type(profile[key]) is not bool:
            raise ValueError("invalid_" + key)
    weights = profile["weights"]
    if not isinstance(weights, dict) or set(weights) != set(CRITERIA):
        raise ValueError("invalid_weights")
    if any(type(value) is not int or not 1 <= value <= 5 for value in weights.values()):
        raise ValueError("invalid_weight_range")


def exclusions(profile: dict, choice: str) -> list[str]:
    reasons = []
    if profile["data_policy"] == "local_only" and choice != "self_hosted":
        reasons.append("Daten duerfen die lokale Zone nicht verlassen")
    if not profile["ops_team"] and choice != "cloud":
        reasons.append("Eigenbetrieb ohne verantwortliches Betriebsteam ausgeschlossen")
    if profile["private_retrieval"] and choice == "cloud":
        reasons.append("Privater Index darf nicht in Cloud-Betrieb wandern")
    if choice == "hybrid" and profile["data_policy"] != "split_allowed":
        reasons.append("Hybrid-Split ist nicht explizit freigegeben")
    if choice == "hybrid" and not profile["external_model_approved"]:
        reasons.append("Externer Modellpfad ist nicht freigegeben")
    if profile["requires_multi_main"] and profile["community_only"] and choice != "cloud":
        reasons.append("Multi-Main ist in Community nicht enthalten; Edition klaeren")
    if profile["third_party_hosting"]:
        reasons.append("Drittanbieter-Hosting erfordert vorgaengige Lizenzklaerung")
    return reasons


def decide(profile: dict) -> dict:
    validate(profile)
    rows = []
    for name in ORDER:
        reasons = exclusions(profile, name)
        terms = {key: profile["weights"][key] * CAPABILITIES[name][key] for key in CRITERIA}
        rows.append({"architecture": name, "eligible": not reasons,
                     "exclusions": reasons, "capabilities": CAPABILITIES[name],
                     "weighted_terms": terms, "score": sum(terms.values()) if not reasons else None})
    eligible = [row for row in rows if row["eligible"]]
    high = max((row["score"] for row in eligible), default=None)
    winners = [row["architecture"] for row in eligible if row["score"] == high]
    selected = winners[0] if len(winners) == 1 else None
    return {"profile_id": profile["id"], "profile_sha256": digest(profile),
            "policy_version": POLICY_VERSION,
            "policy_sha256": digest({"version": POLICY_VERSION, "capabilities": CAPABILITIES,
                                     "criteria": CRITERIA, "exclusion_rules": 7}),
            "status": "decision" if selected else "needs_clarification",
            "selected": selected, "tied": winners if len(winners) > 1 else [],
            "weights": profile["weights"], "candidates": rows,
            "impacts": IMPACTS[selected] if selected else None,
            "open_checks": ["Datenfluesse und Aufbewahrung fachlich freigeben",
                            "Edition und Lizenz fuer konkreten Einsatz bestaetigen",
                            "SLO, RPO/RTO, Kosten und Anbieterbedingungen messen",
                            "Bedrohungsmodell, Wiederherstellung und Exit praktisch testen"]}


def profiles() -> dict[str, dict]:
    rows = json.loads((ROOT / "data/profiles.json").read_text(encoding="utf-8"))["profiles"]
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate_profile_id")
    for row in rows:
        validate(row)
    return result


def all_decisions() -> dict:
    source = profiles()
    return {"dataset_sha256": digest(source), "decisions": [decide(row) for row in source.values()]}


if __name__ == "__main__":
    print(json.dumps(all_decisions(), ensure_ascii=False, indent=2))
