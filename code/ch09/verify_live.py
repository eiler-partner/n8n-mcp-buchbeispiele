"""Compare the tested Python contract with both published native-Python workflows."""

import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from fixtures import CASES
from profiler import profile_csv, profile_csv_pandas


ROOT = Path(__file__).resolve().parent


def compose(*args):
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)}: {(result.stdout + result.stderr)[-4000:]}")
    return result.stdout


def post(url, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=raw, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=40) as response:
        if response.status != 200:
            raise AssertionError(f"Unexpected status {response.status}")
        return json.load(response)


def main():
    env = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)
    compose("stop", "n8n")
    try:
        for kind in ("core", "pandas"):
            compose(
                "run", "--rm", "--no-deps", "n8n", "import:workflow",
                f"--input=/lab/workflows/ch09-{kind}.json",
            )
            compose("run", "--rm", "--no-deps", "n8n", "publish:workflow", f"--id=ch09{kind.title()}")
    finally:
        compose("up", "-d", "--wait", "n8n", "runners")
    for kind, contract in (("core", profile_csv), ("pandas", profile_csv_pandas)):
        for case, csv_text in CASES.items():
            actual = post(
                f"http://127.0.0.1:{env['N8N_PORT']}/webhook/ch09-{kind}",
                {"case": case, "csv_text": csv_text},
            )
            expected = {
                "case": case,
                "status": "ready" if case == "clean" else "review",
                "profile": contract(csv_text),
            }
            if actual != expected:
                raise AssertionError(f"{kind}/{case}: {actual!r} != {expected!r}")
            print(f"PASS: {kind}/{case}: {actual['status']}, {actual['profile']['valid_count']} valid")


if __name__ == "__main__":
    main()
