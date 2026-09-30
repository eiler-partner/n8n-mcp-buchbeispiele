"""Erzeugt lokale Labor-Secrets; überschreibt nie eine vorhandene .env."""

from pathlib import Path
import os
import secrets


LAB = Path(__file__).resolve().parent
TARGET = LAB / ".env"


def create_env(path: Path = TARGET) -> bool:
    if path.exists():
        return False
    content = (
        "# Lokal erzeugt; nicht einchecken oder weitergeben.\n"
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n"
        f"N8N_ENCRYPTION_KEY={secrets.token_urlsafe(36)}\n"
        "LAB_N8N_HOST_PORT=15678\n"
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return False
    return True


if __name__ == "__main__":
    if create_env():
        print("Lokale .env angelegt; Secrets werden nicht ausgegeben.")
    else:
        print("Vorhandene .env unverändert gelassen.")
