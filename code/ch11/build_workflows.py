"""Generate two reviewable revisions of one synthetic n8n workflow."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "workflows"
WORKFLOW_ID = "ch11Review"
WEBHOOK_PATH = "ch11-review"


def node(number, name, kind, version, x, parameters):
    return {
        "parameters": parameters,
        "id": f"11111111-{number:04d}-4000-8000-{number:012d}",
        "name": name,
        "type": f"n8n-nodes-base.{kind}",
        "typeVersion": version,
        "position": [x, 0],
    }


def workflow(threshold):
    if threshold not in (80, 70):
        raise ValueError("Only the two reviewed revisions are supported")
    code = (
        "const body = $input.first().json.body || {};\n"
        "const score = body.score;\n"
        "const caseId = typeof body.case_id === 'string' ? body.case_id : '';\n"
        "if (!Number.isInteger(score) || score < 0 || score > 100 || !caseId) {\n"
        "  return [{json:{case_id:caseId,accepted:false,reason:'invalid_input'}}];\n"
        "}\n"
        f"const accepted = score >= {threshold};\n"
        "return [{json:{case_id:caseId,accepted,reason:accepted?'approved':'manual_review'}}];\n"
    )
    webhook = node(
        1, "Receive Synthetic Case", "webhook", 2.1, -400,
        {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
    )
    webhook["webhookId"] = "11111111-ch11-review"
    nodes = [
        webhook,
        node(2, "Apply Reviewed Rule", "code", 2, -140,
             {"mode": "runOnceForAllItems", "jsCode": code}),
        node(3, "Return Decision", "respondToWebhook", 1.4, 120,
             {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}", "options": {}}),
    ]
    link = lambda target: {"main": [[{"node": target, "type": "main", "index": 0}]]}
    return {
        "id": WORKFLOW_ID,
        "name": "CH11 - reviewed synthetic decision",
        "active": False,
        "nodes": nodes,
        "connections": {
            "Receive Synthetic Case": link("Apply Reviewed Rule"),
            "Apply Reviewed Rule": link("Return Decision"),
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "versionId": f"11111111-1000-4000-8000-{threshold:012d}",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, threshold in (("ch11-baseline.json", 80), ("ch11-candidate.json", 70)):
        path = OUT / name
        path.write_text(json.dumps(workflow(threshold), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
