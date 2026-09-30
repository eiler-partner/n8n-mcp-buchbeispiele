"""Send the synthetic fixture to an explicitly chosen n8n webhook URL."""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_notes.txt"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Exact test or production webhook URL")
    args = parser.parse_args()
    if not args.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        parser.error("This lab accepts loopback URLs only.")
    document = {"filename": FIXTURE.name, "text": FIXTURE.read_text(encoding="utf-8")}
    body = json.dumps(document).encode("utf-8")
    request = Request(args.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=15) as response:
            print(response.status, response.read().decode("utf-8"))
            return 0
    except HTTPError as exc:
        print(exc.code, exc.read().decode("utf-8"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
