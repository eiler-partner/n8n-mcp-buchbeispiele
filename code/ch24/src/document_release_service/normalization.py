from __future__ import annotations

import hashlib
import re

from .models import DocumentInput, NormalizedDocument


WHITESPACE = re.compile(r"[\t\r\f\v ]+")
BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    lines = [WHITESPACE.sub(" ", line).strip() for line in value.splitlines()]
    return BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def normalize_document(
    value: DocumentInput, *, tenant_id: str, correlation_id: str
) -> NormalizedDocument:
    text = normalize_text(value.text)
    digest_input = "\n".join(
        (tenant_id, value.document_id, value.title.strip(), value.source.strip(), text)
    ).encode()
    return NormalizedDocument(
        tenant_id=tenant_id,
        document_id=value.document_id,
        title=value.title.strip(),
        source=value.source.strip(),
        text=text,
        trusted=value.trusted,
        content_hash=hashlib.sha256(digest_input).hexdigest(),
        correlation_id=correlation_id,
    )
