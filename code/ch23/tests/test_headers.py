from __future__ import annotations

import pytest

from prompt_boundary_lab.headers import (
    decode_mcp_header_value,
    header_matches_body,
    validate_mcp_header,
)


def test_plain_ascii_value_is_sent_unchanged() -> None:
    assert validate_mcp_header("Mcp-Param-Priority", "high") == ("Mcp-Param-Priority", "high")


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (" padded ", "=?base64?IHBhZGRlZCA=?="),  # Randleerzeichen: niemals strip()
        ("line1\nline2", "=?base64?bGluZTEKbGluZTI=?="),
        ("Hello, 世界", "=?base64?SGVsbG8sIOS4lueVjA==?="),
        ("=?base64?literal?=", "=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?="),
    ],
)
def test_unsafe_values_are_base64_encoded(value: str, encoded: str) -> None:
    # Beispiele aus der Spezifikation (Streamable HTTP, Value Encoding)
    assert validate_mcp_header("Mcp-Param-Text", value)[1] == encoded
    assert decode_mcp_header_value(encoded) == value


def test_injection_attempt_cannot_reach_http_framing() -> None:
    _, encoded = validate_mcp_header("Mcp-Param-Priority", "safe\r\nX-Evil: yes")
    assert "\r" not in encoded and "\n" not in encoded


def test_types_follow_sep_2243() -> None:
    assert validate_mcp_header("Mcp-Param-Count", 42)[1] == "42"
    assert validate_mcp_header("Mcp-Param-Flag", True)[1] == "true"
    with pytest.raises(ValueError, match="nur string"):
        validate_mcp_header("Mcp-Param-Ratio", 0.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["safe\r\nX-Evil: yes", "bad\x00value", "umlaut-ä"])
def test_server_rejects_raw_invalid_characters(raw: str) -> None:
    with pytest.raises(ValueError, match="Steuerzeichen"):
        decode_mcp_header_value(raw)


def test_server_compares_decoded_header_with_body() -> None:
    assert header_matches_body("=?base64?IHBhZGRlZCA=?=", " padded ")
    assert not header_matches_body("padded", " padded ")  # strip() erzeugt HeaderMismatch


def test_invalid_header_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Headername"):
        validate_mcp_header("Mcp Param", "high")


def test_header_length_is_bounded() -> None:
    with pytest.raises(ValueError, match="zu lang"):
        validate_mcp_header("Mcp-Param-Note", "x" * 257)
