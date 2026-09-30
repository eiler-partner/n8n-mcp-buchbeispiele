"""Werte aus ``x-mcp-header`` nach SEP-2243 (MCP 2026-07-28) behandeln.

Client: wandelt einen Toolparameter in einen Headerwert um und kodiert ihn
mit Base64, sobald er nicht als schlichtes ASCII transportiert werden kann.
Server: lehnt ungültige Rohwerte ab, dekodiert und vergleicht mit dem Body.
"""

from __future__ import annotations

import base64
import binascii
import re

HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
SENTINEL = re.compile(r"^=\?base64\?(.*)\?=$", re.DOTALL)
MAX_SAFE_INTEGER = 2**53 - 1


def _is_plain_ascii(value: str) -> bool:
    """Sichtbares ASCII, Leerzeichen und Tab; keine Randleerzeichen, kein Sentinel."""
    if value != value.strip(" \t"):
        return False
    if SENTINEL.fullmatch(value):
        return False
    return all(0x21 <= ord(char) <= 0x7E or char in " \t" for char in value)


def encode_mcp_header_value(value: str | int | bool) -> str:
    """Typumwandlung und Kodierung laut SEP-2243; ``number`` ist nicht erlaubt."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise ValueError("Ganzzahl außerhalb des sicheren Bereichs")
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ValueError("x-mcp-header erlaubt nur string, integer und boolean")
    if _is_plain_ascii(text):
        return text
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"=?base64?{encoded}?="


def validate_mcp_header(name: str, value: str | int | bool, *, max_length: int = 256) -> tuple[str, str]:
    """Clientseite: Headername prüfen, Wert kodieren, Größe begrenzen."""
    if not HEADER_NAME.fullmatch(name):
        raise ValueError("ungueltiger Headername")
    encoded = encode_mcp_header_value(value)
    if len(encoded) > max_length:
        raise ValueError("Headerwert zu lang")
    return name, encoded


def decode_mcp_header_value(raw: str) -> str:
    """Serverseite: Rohwert prüfen und gegebenenfalls Base64 dekodieren."""
    if any(not (0x20 <= ord(char) <= 0x7E or char == "\t") for char in raw):
        raise ValueError("Steuerzeichen oder Nicht-ASCII im Headerwert")
    match = SENTINEL.fullmatch(raw)
    if not match:
        return raw
    try:
        return base64.b64decode(match.group(1), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("ungültige Base64-Kodierung im Headerwert") from error


def header_matches_body(raw: str, body_value: str | int | bool) -> bool:
    """HeaderMismatch-Prüfung: dekodierter Header muss exakt dem Body entsprechen."""
    decoded = decode_mcp_header_value(raw)
    if isinstance(body_value, str):
        return decoded == body_value
    return decoded == encode_mcp_header_value(body_value)
