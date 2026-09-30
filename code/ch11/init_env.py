"""Create chapter-local Docker settings once; never replace an existing key."""

import os
import secrets
from pathlib import Path


def initialize(path):
    if path.exists():
        return False
    content = (
        f"DEV_ENCRYPTION_KEY={secrets.token_urlsafe(48)}\n"
        f"TEST_ENCRYPTION_KEY={secrets.token_urlsafe(48)}\n"
        "DEV_PORT=15685\n"
        "TEST_PORT=15686\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    return True


if __name__ == "__main__":
    target = Path(__file__).with_name(".env")
    print("Created private .env" if initialize(target) else "Existing .env preserved")
