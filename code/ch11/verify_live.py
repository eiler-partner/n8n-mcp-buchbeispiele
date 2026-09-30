"""Prove export, review, promotion, and rollback on two local n8n instances."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from build_workflows import WEBHOOK_PATH, WORKFLOW_ID, workflow
from review_contract import canonical, canonical_json


ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT / ".exchange"
ENV = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)
PORTS = {"dev": ENV["DEV_PORT"], "test": ENV["TEST_PORT"]}
ARTIFACTS = {"baseline": "ch11-baseline.json", "candidate": "ch11-candidate.json"}


def run(*args, cwd=ROOT, allowed=(0,)):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode not in allowed:
        raise RuntimeError(f"{' '.join(args)} failed:\n{(result.stdout + result.stderr)[-3000:]}")
    return result


def compose(*args):
    return run("docker", "compose", *args)


def deploy(instance, revision):
    compose("stop", instance)
    compose("run", "--rm", "--no-deps", instance, "import:workflow",
            f"--input=/lab/workflows/{ARTIFACTS[revision]}")
    compose("run", "--rm", "--no-deps", instance, "publish:workflow", f"--id={WORKFLOW_ID}")
    compose("up", "-d", "--wait", instance)


def export(instance, label):
    compose("stop", instance)
    filename = f"{label}.raw.json"
    compose("run", "--rm", "--no-deps", instance, "export:workflow",
            f"--id={WORKFLOW_ID}", f"--output=/exchange/{filename}")
    return json.loads((EXCHANGE / filename).read_text(encoding="utf-8"))


def request(instance, score, *, timeout=20):
    url = f"http://127.0.0.1:{PORTS[instance]}/webhook/{WEBHOOK_PATH}"
    body = json.dumps({"case_id": f"C-{score}", "score": score}).encode()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=10) as response:
                assert response.status == 200
                return json.load(response)
        except HTTPError as error:
            if error.code != 404:
                raise
            time.sleep(0.5)
    raise AssertionError(f"{instance} webhook was not ready")


def wait_for_published_rule(instance, revision, *, timeout=30):
    """A healthy process is not proof that the new published rule is serving."""
    expected = revision == "candidate"
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = request(instance, 75)
        if last["accepted"] is expected:
            return
        time.sleep(0.5)
    raise AssertionError(f"{instance}: {revision} was not serving; last response: {last}")


def check_cases(instance, revision):
    expected_75 = revision == "candidate"
    for score, accepted, reason in (
        (85, True, "approved"),
        (75, expected_75, "approved" if expected_75 else "manual_review"),
        (101, False, "invalid_input"),
    ):
        result = request(instance, score)
        assert result == {"case_id": f"C-{score}", "accepted": accepted, "reason": reason}, result


def review_in_git(before, after):
    before_text, after_text = canonical_json(before), canonical_json(after)
    baseline_path = EXCHANGE / "baseline.review.json"
    candidate_path = EXCHANGE / "candidate.review.json"
    baseline_path.write_text(before_text, encoding="utf-8")
    candidate_path.write_text(after_text, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="ch11-git-review-") as directory:
        repo = Path(directory)
        artifact = repo / "workflow.json"
        run("git", "init", "-q", cwd=repo)
        artifact.write_text(before_text, encoding="utf-8")
        run("git", "add", "workflow.json", cwd=repo)
        run("git", "-c", "user.name=Chapter 11 Lab", "-c", "user.email=lab@example.invalid",
            "commit", "-q", "-m", "Approved baseline", cwd=repo)
        artifact.write_text(after_text, encoding="utf-8")
        run("git", "diff", "--check", cwd=repo)
        patch = run("git", "diff", "--", "workflow.json", cwd=repo).stdout
        assert "score >= 80" in patch and "score >= 70" in patch
        (EXCHANGE / "review.patch").write_text(patch, encoding="utf-8")
        run("git", "add", "workflow.json", cwd=repo)
        run("git", "-c", "user.name=Chapter 11 Lab", "-c", "user.email=lab@example.invalid",
            "commit", "-q", "-m", "Reviewed candidate", cwd=repo)
        run("git", "-c", "user.name=Chapter 11 Lab", "-c", "user.email=lab@example.invalid",
            "revert", "--no-edit", "HEAD", cwd=repo)
        assert artifact.read_text(encoding="utf-8") == before_text
    return patch


def main():
    EXCHANGE.mkdir(exist_ok=True)
    for revision, threshold in (("baseline", 80), ("candidate", 70)):
        path = ROOT / "workflows" / ARTIFACTS[revision]
        assert json.loads(path.read_text(encoding="utf-8")) == workflow(threshold)

    deploy("dev", "baseline")
    wait_for_published_rule("dev", "baseline")
    check_cases("dev", "baseline")
    before = export("dev", "dev-baseline")
    assert canonical(before) == canonical(workflow(80))
    print("PASS Dev baseline: imported, published, tested, and exported")

    deploy("dev", "candidate")
    wait_for_published_rule("dev", "candidate")
    check_cases("dev", "candidate")
    after = export("dev", "dev-candidate")
    assert canonical(after) == canonical(workflow(70))
    patch = review_in_git(before, after)
    assert patch.count("score >= 80") == 1 and patch.count("score >= 70") == 1
    print("PASS Git review: only the rule changes; revert restores baseline")

    deploy("test", "candidate")
    wait_for_published_rule("test", "candidate")
    check_cases("test", "candidate")
    print("PASS Test promotion: candidate behaves as reviewed")

    deploy("test", "baseline")
    wait_for_published_rule("test", "baseline")
    check_cases("test", "baseline")
    print("PASS Test rollback: approved baseline behavior restored")
    compose("up", "-d", "--wait", "dev", "test")


if __name__ == "__main__":
    main()
