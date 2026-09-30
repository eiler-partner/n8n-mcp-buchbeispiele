"""Didactic architecture review; policies are specific to this example."""

import argparse
import json
from pathlib import Path


REQUIRED_COMPONENT = {"id", "role", "zone", "owner", "input", "output"}
REQUIRED_FLOW = {"from", "to", "contract", "classification", "control", "approval"}
KNOWN_ZONES = {"workplace", "internal", "provider"}


def validate(architecture):
    errors = []
    components = architecture.get("components", [])
    flows = architecture.get("flows", [])
    classes = architecture.get("classification_order", [])
    if not isinstance(classes, list) or not classes or len(classes) != len(set(classes)):
        errors.append("classification_order muss eine eindeutige Liste sein")
        classes = []

    by_id = {}
    for number, component in enumerate(components, 1):
        if not isinstance(component, dict):
            errors.append(f"Komponente {number}: kein Objekt")
            continue
        missing = REQUIRED_COMPONENT - component.keys()
        if missing:
            errors.append(f"Komponente {number}: Felder fehlen: {', '.join(sorted(missing))}")
            continue
        identifier = component["id"]
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"Komponente {number}: leere ID")
            continue
        if identifier in by_id:
            errors.append(f"Komponente {identifier}: ID doppelt")
        by_id[identifier] = component
        if component["zone"] not in KNOWN_ZONES:
            errors.append(f"Komponente {identifier}: unbekannte Zone")
        for field in ("role", "owner", "input", "output"):
            if not isinstance(component[field], str) or not component[field].strip():
                errors.append(f"Komponente {identifier}: {field} ist leer")

    for number, flow in enumerate(flows, 1):
        if not isinstance(flow, dict):
            errors.append(f"Datenfluss {number}: kein Objekt")
            continue
        missing = REQUIRED_FLOW - flow.keys()
        if missing:
            errors.append(f"Datenfluss {number}: Felder fehlen: {', '.join(sorted(missing))}")
            continue
        source = by_id.get(flow["from"])
        target = by_id.get(flow["to"])
        if source is None or target is None:
            errors.append(f"Datenfluss {number}: unbekannter Endpunkt")
            continue
        for field in ("contract", "control"):
            if not isinstance(flow[field], str) or not flow[field].strip():
                errors.append(f"Datenfluss {number}: {field} ist leer")
        if flow["classification"] not in classes:
            errors.append(f"Datenfluss {number}: unbekannte Datenklasse")
        if not isinstance(flow["approval"], bool):
            errors.append(f"Datenfluss {number}: approval muss boolesch sein")
        if (target["zone"] == "provider" and
                flow["classification"] == "confidential"):
            errors.append(f"Datenfluss {number}: vertrauliche Rohdaten verlassen die interne Zone")
        if target["role"] == "write_api" and not flow["approval"]:
            errors.append(f"Datenfluss {number}: Schreib-API ohne explizite Freigabe")
        if target["role"] == "write_api" and source["role"] != "policy":
            errors.append(f"Datenfluss {number}: Schreib-API nur ueber Pruefdienst")
        if source["role"] == "model" and target["role"] == "write_api":
            errors.append(f"Datenfluss {number}: Modell darf nicht direkt schreiben")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    architecture = json.loads(args.path.read_text(encoding="utf-8"))
    errors = validate(architecture)
    if errors:
        for error in errors:
            print(f"FEHLER: {error}")
        raise SystemExit(1)
    print(f"OK: {len(architecture['components'])} Komponenten, "
          f"{len(architecture['flows'])} Datenfluesse geprueft")


if __name__ == "__main__":
    main()
