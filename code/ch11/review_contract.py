"""Small, deliberately conservative checks for reviewable workflow artifacts."""

import json


def canonical(workflow):
    """Keep the review surface; discard export timestamps and runtime metadata."""
    if isinstance(workflow, list):
        if len(workflow) != 1:
            raise ValueError("Expected one workflow per artifact")
        workflow = workflow[0]
    keys = ("id", "name", "nodes", "connections", "settings")
    return {key: workflow[key] for key in keys}


def audit(workflow):
    """Reject known secret-bearing fields; a human review remains mandatory."""
    if isinstance(workflow, list):
        if len(workflow) != 1:
            raise ValueError("Expected one workflow per artifact")
        workflow = workflow[0]
    forbidden = {"credentials", "authorization", "password", "apikey", "accesstoken", "clientsecret"}
    auth_headers = {"authorization", "proxy-authorization", "x-api-key", "api-key"}
    problems = []

    def walk(value, path):
        if isinstance(value, dict):
            if isinstance(value.get("name"), str) and value["name"].lower() in auth_headers:
                problems.append(f"{path}.name={value['name']}")
            for key, child in value.items():
                next_path = f"{path}.{key}"
                if key.lower() in forbidden:
                    problems.append(next_path)
                walk(child, next_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(workflow, "$")
    if problems:
        raise ValueError("Potential secret fields: " + ", ".join(problems))
    return True


def canonical_json(workflow):
    audit(workflow)
    return json.dumps(canonical(workflow), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
