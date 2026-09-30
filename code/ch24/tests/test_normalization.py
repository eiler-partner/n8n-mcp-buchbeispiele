from __future__ import annotations

from document_release_service.models import DocumentInput
from document_release_service.normalization import normalize_document, normalize_text


def fixture(text: str = "Zeile   eins.\n\n\nZeile zwei.") -> DocumentInput:
    return DocumentInput(
        document_id="DOC-001",
        title="  Prüfdokument  ",
        source="fixture:test.txt",
        text=text,
        trusted=True,
    )


def test_whitespace_is_normalized() -> None:
    assert normalize_text("a   b\n\n\n c") == "a b\n\nc"


def test_hash_is_deterministic() -> None:
    left = normalize_document(fixture(), tenant_id="t1", correlation_id="c1")
    right = normalize_document(fixture(), tenant_id="t1", correlation_id="c2")
    assert left.content_hash == right.content_hash


def test_hash_is_tenant_bound() -> None:
    left = normalize_document(fixture(), tenant_id="t1", correlation_id="c1")
    right = normalize_document(fixture(), tenant_id="t2", correlation_id="c1")
    assert left.content_hash != right.content_hash


def test_title_is_stripped() -> None:
    value = normalize_document(fixture(), tenant_id="t1", correlation_id="c1")
    assert value.title == "Prüfdokument"
