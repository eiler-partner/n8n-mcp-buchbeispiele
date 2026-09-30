from __future__ import annotations

import argparse
from pathlib import Path

from .config import build_adapter, get_settings
from .domain import ExtractionRequest
from .service import ExtractionService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the chapter-12 extraction contract.")
    parser.add_argument("path", type=Path, help="UTF-8 text file containing one invoice")
    parser.add_argument("--document-id", default="demo-invoice")
    args = parser.parse_args()

    request = ExtractionRequest(
        document_id=args.document_id,
        text=args.path.read_text(encoding="utf-8"),
    )
    service = ExtractionService(primary=build_adapter(get_settings()))
    print(service.extract(request).model_dump_json(indent=2))
