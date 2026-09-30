"""Build reproducible n8n 2.40.7 workflows for the document-fault lab."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "n8n" / "workflows"
NAMESPACE = "10101010"


def node(number, name, kind, version, x, y, parameters, **extra):
    return {
        "parameters": parameters,
        "id": f"{NAMESPACE}-{number:04d}-4000-8000-{number:012d}",
        "name": name,
        "type": f"n8n-nodes-base.{kind}",
        "typeVersion": version,
        "position": [x, y],
        **extra,
    }


def connect(target, index=0):
    return {"node": target, "type": "main", "index": index}


def one(target):
    return {"main": [[connect(target)]]}


def branch(yes, no):
    return {"main": [[connect(yes)], [connect(no)]]}


def request(url, body, *, full=False, timeout=1500):
    parameters = {
        "method": "POST",
        "url": f"http://service:8079/{url}",
        "sendBody": True,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": body,
        "options": {"timeout": timeout},
    }
    if full:
        parameters["options"]["response"] = {
            "response": {"fullResponse": True, "neverError": True}
        }
    return parameters


def boolean_if(expression):
    return {
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "strict",
                "version": 2,
            },
            "conditions": [
                {
                    "id": "10-if-boolean",
                    "leftValue": expression,
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }
            ],
            "combinator": "and",
        },
        "options": {},
    }


DOCUMENT_BODY = "={{ JSON.stringify($('Receive Document').first().json.body) }}"
DOCUMENT_ID = "$('Receive Document').first().json.body.doc_id"
FINALIZE = (
    "const response = $input.first().json;\n"
    "const document = $('Receive Document').first().json.body;\n"
    "const status = response.statusCode;\n"
    "if (status === 200) return [{json:{doc_id:document.doc_id,kind:'prepared'}}];\n"
    "if (status === 422) return [{json:{doc_id:document.doc_id,kind:'quarantine',"
    "reason:'schema_invalid'}}];\n"
    "if (status === 503) return [{json:{doc_id:document.doc_id,kind:'quarantine',"
    "reason:'retry_exhausted'}}];\n"
    "throw new Error('unexpected_analysis_status_' + status);\n"
)


def main_workflow():
    nodes = [
        node(
            1, "Receive Document", "webhook", 2.1, -1060, 0,
            {"httpMethod": "POST", "path": "ch10-document", "responseMode": "onReceived", "options": {}},
            webhookId="10101010-ch10-document",
        ),
        node(2, "Analyze 1", "httpRequest", 4.4, -820, 0, request("analyze", DOCUMENT_BODY, full=True)),
        node(3, "Retryable 1?", "if", 2.2, -580, 0, boolean_if("={{ $json.statusCode === 503 }}")),
        node(4, "Wait 1", "wait", 1.1, -360, -140, {"resume": "timeInterval", "amount": 1, "unit": "seconds"}),
        node(5, "Analyze 2", "httpRequest", 4.4, -140, -140, request("analyze", DOCUMENT_BODY, full=True)),
        node(6, "Retryable 2?", "if", 2.2, 80, -140, boolean_if("={{ $json.statusCode === 503 }}")),
        node(7, "Wait 2", "wait", 1.1, 300, -260, {"resume": "timeInterval", "amount": 2, "unit": "seconds"}),
        node(8, "Analyze 3", "httpRequest", 4.4, 520, -260, request("analyze", DOCUMENT_BODY, full=True)),
        node(9, "Classify", "code", 2, 760, 40, {"mode": "runOnceForAllItems", "jsCode": FINALIZE}),
        node(10, "Prepared?", "if", 2.2, 980, 40, boolean_if("={{ $json.kind === 'prepared' }}")),
        node(
            11, "Quarantine", "httpRequest", 4.4, 1200, 220,
            request(
                "quarantine",
                "={{ JSON.stringify({doc_id:$json.doc_id,reason:$json.reason}) }}",
            ),
        ),
        node(
            12, "Register Approval", "httpRequest", 4.4, 1200, -100,
            request(
                "approval-link",
                f"={{{{ JSON.stringify({{doc_id:{DOCUMENT_ID},url:$execution.resumeFormUrl}}) }}}}",
            ),
        ),
        node(
            13, "Wait For Local Approval", "wait", 1.1, 1430, -100,
            {
                "resume": "form",
                "formTitle": "Dokument zur Freigabe",
                "formDescription": "Nur synthetische Testdaten. Bitte Freigeben oder Ablehnen waehlen.",
                "formFields": {
                    "values": [
                        {
                            "fieldLabel": "Decision",
                            "fieldType": "dropdown",
                            "fieldOptions": {"values": [{"option": "Approve"}, {"option": "Deny"}]},
                            "requiredField": True,
                        }
                    ]
                },
                "options": {},
            },
            webhookId="10101010-ch10-approval",
        ),
        node(
            14, "Approved?", "if", 2.2, 1660, -100,
            boolean_if("={{ $json.Decision === 'Approve' }}"),
        ),
        node(
            15, "Publish Idempotently", "httpRequest", 4.4, 2140, -210,
            request(
                "publish", f"={{{{ JSON.stringify({{doc_id:{DOCUMENT_ID}}}) }}}}",
                timeout=1000,
            ),
            retryOnFail=True, maxTries=3, waitBetweenTries=1000,
        ),
        node(
            16, "Record Denial", "httpRequest", 4.4, 1900, 20,
            request("deny", f"={{{{ JSON.stringify({{doc_id:{DOCUMENT_ID}}}) }}}}"),
        ),
        node(
            17, "Record Approval", "httpRequest", 4.4, 1900, -210,
            request("approve", f"={{{{ JSON.stringify({{doc_id:{DOCUMENT_ID}}}) }}}}"),
        ),
    ]
    connections = {
        "Receive Document": one("Analyze 1"),
        "Analyze 1": one("Retryable 1?"),
        "Retryable 1?": branch("Wait 1", "Classify"),
        "Wait 1": one("Analyze 2"),
        "Analyze 2": one("Retryable 2?"),
        "Retryable 2?": branch("Wait 2", "Classify"),
        "Wait 2": one("Analyze 3"),
        "Analyze 3": one("Classify"),
        "Classify": one("Prepared?"),
        "Prepared?": branch("Register Approval", "Quarantine"),
        "Register Approval": one("Wait For Local Approval"),
        "Wait For Local Approval": one("Approved?"),
        "Approved?": branch("Record Approval", "Record Denial"),
        "Record Approval": one("Publish Idempotently"),
    }
    return {
        "id": "ch10Main",
        "name": "CH10 - document pipeline with bounded recovery",
        "active": False,
        "nodes": nodes,
        "connections": connections,
        "pinData": {},
        "settings": {
            "executionOrder": "v1",
            "errorWorkflow": "ch10Error",
            "saveExecutionProgress": True,
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
        },
        "versionId": "10101010-1000-4000-8000-000000000001",
    }


def error_workflow():
    nodes = [
        node(91, "Error Trigger", "errorTrigger", 1, -320, 0, {}),
        node(
            92, "Record Alert", "httpRequest", 4.4, -80, 0,
            request(
                "alert",
                "={{ JSON.stringify({workflow_id:String($json.workflow.id || 'unknown'),"
                "execution_id:String($json.execution?.id || $json.trigger?.error?.timestamp || 'unknown'),"
                "message:String($json.execution?.error?.message || $json.trigger?.error?.message || 'failure').slice(0,200)}) }}",
            ),
        ),
    ]
    return {
        "id": "ch10Error",
        "name": "CH10 - central error record",
        "active": False,
        "nodes": nodes,
        "connections": {"Error Trigger": one("Record Alert")},
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "versionId": "10101010-1000-4000-8000-000000000091",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("ch10-error.json", error_workflow()), ("ch10-main.json", main_workflow())):
        destination = OUT / name
        destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
