"""Create chapter-local secrets once; never overwrite an existing .env."""

import os
import secrets
from pathlib import Path


def initialize(path):
    if path.exists():
        return False
    content = (
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n"
        f"N8N_ENCRYPTION_KEY={secrets.token_urlsafe(48)}\n"
        "N8N_PORT=15684\n"
        "LAB_PORT=18070\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    return True


if __name__ == "__main__":
    target = Path(__file__).with_name(".env")
    print("Created private .env" if initialize(target) else "Existing .env preserved")
