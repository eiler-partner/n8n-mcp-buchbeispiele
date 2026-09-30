"""Local-only demonstration: issue a short-lived role token from your test key."""
from __future__ import annotations

import sys
from case_service import issue_token

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python token_cli.py requester|reviewer subject")
    print(issue_token(sys.argv[2], sys.argv[1]))
