"""Read-only, allowlisted source acquisition with fail-closed policy gates."""
from __future__ import annotations

import csv
import hashlib
import os
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).parent
MAX_SOURCE_BYTES = 65536
USER_AGENT = "ch44-lab"
SOURCES = {
    "api-quarter": {"kind": "http", "path": "/api/quarter", "terms": "approved"},
    "web-briefing": {"kind": "http", "path": "/web/briefing", "terms": "approved"},
    "file-regions": {"kind": "file", "file": "regions.csv", "terms": "approved"},
    "web-robots-blocked": {"kind": "http", "path": "/web/private", "terms": "approved"},
    "web-tdm-blocked": {"kind": "http", "path": "/web/tdm", "terms": "approved"},
    "web-terms-blocked": {"kind": "http", "path": "/web/terms", "terms": "review_required"},
    "web-redirect-blocked": {"kind": "http", "path": "/web/redirect", "terms": "approved"},
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def fetch(url: str) -> tuple[bytes, object]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with OPENER.open(request, timeout=4) as response:
        if response.headers.get("tdm-reservation") == "1":
            # A reservation is observable in the response header; do not ingest its body.
            return b"", response.headers
        data = response.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError("source_too_large")
        return data, response.headers


def head(url: str) -> object:
    """Header-only preflight. A HEAD response carries status and headers but no body."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with OPENER.open(request, timeout=4) as response:
        return response.headers


def tdm_block(headers) -> str | None:
    value = headers.get("tdm-reservation")
    if value == "1":
        return "tdm_reserved"
    if value not in ("0", None):
        return "tdm_unknown"
    return None


def read_source(source_id: str) -> dict:
    if not isinstance(source_id, str) or source_id not in SOURCES:
        raise ValueError("source_not_allowlisted")
    item = SOURCES[source_id]
    observed = datetime.now(timezone.utc).isoformat()
    base = {"source_id": source_id, "kind": item["kind"],
            "retrieved_at_utc": observed, "transfer_bytes": 0}
    if item["terms"] != "approved":
        return dict(base, status="blocked", reason="terms_review_required")
    if item["kind"] == "file":
        # The path comes only from the fixed registry, never from the request.
        path = ROOT / "data" / item["file"]
        raw = path.read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("source_too_large")
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8"))))
        published = {row["published_at_utc"] for row in rows}
        if len(published) != 1:
            raise ValueError("ambiguous_file_publication")
        return dict(base, status="accepted", uri="fixture://regions.csv",
                    media_type="text/csv", raw_text=raw.decode("utf-8"),
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    published_at_utc=published.pop(), transfer_bytes=len(raw))

    fixture_base = os.getenv("CH44_FIXTURE_BASE", "http://fixtures:8144").rstrip("/")
    if not fixture_base.startswith("http://"):
        raise ValueError("invalid_fixture_base")
    robots_raw, _ = fetch(fixture_base + "/robots.txt")
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(robots_raw.decode("utf-8").splitlines())
    transferred = len(robots_raw)
    url = fixture_base + item["path"]
    if not parser.can_fetch(USER_AGENT, url):
        return dict(base, status="blocked", reason="robots_disallow", transfer_bytes=transferred)
    try:
        # The TDM decision needs only the header: HEAD first, GET only if no reservation.
        reason = tdm_block(head(url))
        raw, headers = (b"", None) if reason else fetch(url)
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            return dict(base, status="blocked", reason="redirect_blocked", transfer_bytes=transferred)
        raise
    if reason is None:
        transferred += len(raw)
        # Fail closed if the GET headers contradict the HEAD preflight.
        reason = tdm_block(headers)
    if reason:
        return dict(base, status="blocked", reason=reason, transfer_bytes=transferred)
    published = headers.get("X-Published-At")
    if not published:
        raise ValueError("missing_publication_time")
    return dict(base, status="accepted", uri="fixture://" + item["path"].lstrip("/"),
                media_type=headers.get_content_type(), raw_text=raw.decode("utf-8"),
                raw_sha256=hashlib.sha256(raw).hexdigest(),
                published_at_utc=published, transfer_bytes=transferred)
