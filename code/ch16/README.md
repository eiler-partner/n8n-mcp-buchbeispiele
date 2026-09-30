# Kapitel 16: Transport- und Versionslabor

Ein synthetischer MCP-Dienst liefert dasselbe Toolresultat über `stdio` und
Streamable HTTP. Der HTTP-Modus bindet nur an `127.0.0.1`, arbeitet ohne
Protokollsitzung und gibt für kurze Aufrufe JSON zurück. Der Negativtest sendet
die unbekannte Revision `1900-01-01` konsistent in Header und Body. Erwartet
werden HTTP 400 und JSON-RPC `-32022` (`UnsupportedProtocolVersion`). Das ist
kein HeaderMismatch-Test und kein SSE-Test.

## Ausführen

```bash
UV_CACHE_DIR=/tmp/buch-ch16-uv-cache uv run --frozen python -m mcp_transport_lab.verify
UV_CACHE_DIR=/tmp/buch-ch16-uv-cache uv run --frozen pytest -q
docker compose run --build --rm transport-lab
```

Der Docker-Durchlauf verwendet ausschließlich die Loopback-Kommunikation
innerhalb des Containers (`network_mode: none`) und hinterlässt keinen
laufenden Laborcontainer. Es gibt weder echte Tickets noch externe
Zugangsdaten. Der Test beendet seinen HTTP-Subprozess auch im Fehlerfall.

Getesteter Stand: Python 3.12, MCP-Python-SDK `mcp==2.2.0`,
Protokollrevision `2026-07-28`.
