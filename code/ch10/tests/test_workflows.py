import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_workflows import error_workflow, main_workflow


def test_checked_in_workflows_match_generator():
    for name, expected in (("ch10-error.json", error_workflow()), ("ch10-main.json", main_workflow())):
        actual = json.loads((ROOT / "n8n" / "workflows" / name).read_text(encoding="utf-8"))
        assert actual == expected


def test_publish_retry_is_node_setting_not_http_parameter():
    workflow = main_workflow()
    publish = next(node for node in workflow["nodes"] if node["name"] == "Publish Idempotently")
    assert (publish["retryOnFail"], publish["maxTries"], publish["waitBetweenTries"]) == (True, 3, 1000)
    assert "retryOnFail" not in publish["parameters"]
    assert workflow["settings"]["errorWorkflow"] == error_workflow()["id"]
