"""Generate n8n workflows from the tested Python contract; no code duplication."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "profiler.py").read_text(encoding="utf-8")
OUT = ROOT / "n8n" / "workflows"


def workflow(kind):
    key = "1" if kind == "core" else "2"
    function = "profile_csv" if kind == "core" else "profile_csv_pandas"
    adapter = (
        "\nresult = []\n"
        "for index, item in enumerate(_items):\n"
        "    body = item['json']['body']\n"
        "    if not isinstance(body, dict) or set(body) != {'case', 'csv_text'}:\n"
        "        raise ValueError('request_contract')\n"
        f"    summary = {function}(body['csv_text'])\n"
        "    result.append({'json': {'case': body['case'], 'profile': summary}, "
        "'pairedItem': {'item': index}})\n"
        "return result\n"
    )
    gate = (
        "payload = _item['json']\n"
        "return {'json': {'case': payload['case'], "
        "'status': 'ready' if payload['profile']['invalid_count'] == 0 else 'review', "
        "'profile': payload['profile']}}\n"
    )
    nodes = [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": f"ch09-{kind}",
                "responseMode": "lastNode",
                "options": {},
            },
            "id": f"09090909-00{key}1-4000-8000-0000000000{key}1",
            "name": "CSV request",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [-400, 0],
            "webhookId": f"09090909-ch09-{kind}",
        },
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "language": "pythonNative",
                "pythonCode": SOURCE + adapter,
            },
            "id": f"09090909-00{key}2-4000-8000-0000000000{key}2",
            "name": "Profile CSV",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-120, 0],
        },
        {
            "parameters": {
                "mode": "runOnceForEachItem",
                "language": "pythonNative",
                "pythonCode": gate,
            },
            "id": f"09090909-00{key}3-4000-8000-0000000000{key}3",
            "name": "Quality gate",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [160, 0],
        },
    ]
    return {
        "id": f"ch09{kind.title()}",
        "name": f"CH09 - CSV profile {kind}",
        "active": False,
        "nodes": nodes,
        "connections": {
            "CSV request": {"main": [[{"node": "Profile CSV", "type": "main", "index": 0}]]},
            "Profile CSV": {"main": [[{"node": "Quality gate", "type": "main", "index": 0}]]},
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "versionId": f"09090909-1000-4000-8000-00000000000{key}",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for kind in ("core", "pandas"):
        destination = OUT / f"ch09-{kind}.json"
        destination.write_text(
            json.dumps(workflow(kind), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
