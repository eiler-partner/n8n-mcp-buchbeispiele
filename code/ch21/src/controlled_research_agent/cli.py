from __future__ import annotations

import argparse

from .config import Settings
from .domain import RunRequest
from .factory import build_controller


def main() -> None:
    parser = argparse.ArgumentParser(description="Kontrollierter Read-only-Recherche-Agent")
    parser.add_argument("question")
    args = parser.parse_args()
    settings = Settings()
    report = build_controller(settings).run(
        RunRequest(question=args.question, limits=settings.limits())
    )
    print(report.model_dump_json(indent=2))
