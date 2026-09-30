"""Run the imported workflows in real n8n and compare to the Python oracle."""

import json
import subprocess
from pathlib import Path

from data import CASES, expected_summary


ROOT = Path(__file__).resolve().parent


def compose(*args, capture=False):
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {(result.stdout or '')[-4000:]}")
    return result.stdout or ""


def workflow_run(workflow_id, final_node):
    output = compose("run", "--rm", "--no-deps", "n8n", "execute", f"--id={workflow_id}", capture=True)
    marker = "Execution was successful:\n====================================\n"
    if marker not in output:
        raise AssertionError(f"Success marker missing: {output[-4000:]}")
    execution, _ = json.JSONDecoder().raw_decode(output.split(marker, 1)[1].lstrip())
    run_data = execution["data"]["resultData"]["runData"]
    result_items = run_data[final_node][-1]["data"]["main"][0]
    return [item["json"] for item in result_items], run_data


def main():
    compose("stop", "n8n")
    try:
        # n8n 2.40 materializes CLI publications when the service next starts.
        compose("run", "--rm", "--no-deps", "n8n", "publish:workflow", "--id=ch07Processor")
        compose("run", "--rm", "--no-deps", "n8n", "publish:workflow", "--id=ch07Parent")
        compose("up", "-d", "--wait", "n8n")
        compose("stop", "n8n")

        actual, _ = workflow_run("ch07Parent", "Process One Envelope")
        expected = [expected_summary(case) for case in CASES]
        if actual != expected:
            raise AssertionError(f"Sub-workflow contract differs:\nactual={actual}\nexpected={expected}")
        print("PASS: empty, single, large and all-filtered contracts")

        batch, runs = workflow_run("ch07Batches", "Done Summary")
        if batch != [{"processed_count": 7, "ids": [f"B-{i}" for i in range(1, 8)]}]:
            raise AssertionError(f"Unexpected batch result: {batch}")
        sizes = [len(run["data"]["main"][0]) for run in runs["Process Batch"]]
        if sizes != [3, 3, 1]:
            raise AssertionError(f"Unexpected batch sizes: {sizes}")
        print("PASS: batch sizes 3, 3, 1 and seven returned items")
    finally:
        compose("up", "-d", "--wait", "n8n")


if __name__ == "__main__":
    main()
