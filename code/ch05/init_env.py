"""Generate local chapter-5 secrets without replacing an existing file."""

from pathlib import Path
import os
import secrets

TARGET = Path(__file__).resolve().parent / ".env"


def create_env(path: Path = TARGET) -> bool:
    if path.exists():
        return False
    content = (
        "# Local chapter-5 lab only; do not commit or share.\n"
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n"
        f"N8N_ENCRYPTION_KEY={secrets.token_urlsafe(36)}\n"
        "N8N_PORT=15679\n"
        "ANALYZER_PORT=18055\n"
    )
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return False
    return True


if __name__ == "__main__":
    print("Local .env created." if create_env() else "Existing .env left unchanged.")
