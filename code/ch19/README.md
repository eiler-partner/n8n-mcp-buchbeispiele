# Kapitel 19: MCP-Clients und Contract Tests

Das Lab enthält einen Python-Client für mehrere MCP-Server, explizite
Tool-Allowlists, einen überprüften Vertragssnapshot, Fehlerfixtures und
Inspector-Smoke-Tests. Es verwendet Python 3.12 und `mcp==2.2.0`.

Die Tests behandeln beide Protokollgenerationen ausdrücklich: Ein moderner
Client beobachtet und vervollständigt ein `input_required`-Ergebnis, während
ein Legacy-Client den Handshake-Vertrag von `2025-11-25` aushandelt.

## Schneller Test

```bash
uv sync --frozen --dev
uv run pytest
```

Der Vertragssnapshot ist absichtlich versioniert. Eine Änderung wird erst nach
fachlichem Review übernommen:

```bash
uv run mcp-contract-snapshot
uv run mcp-contract-snapshot --write contracts/policy-server.json
```

## HTTP und Docker

```bash
docker compose up -d --build --wait
uv run mcp-contract-client --url http://127.0.0.1:8000/mcp
docker compose down
```

## Inspector CLI

```bash
npx -y @modelcontextprotocol/inspector@2.8.0 --cli \
  http://127.0.0.1:8000/mcp --transport http \
  --method tools/list --format json
```

Die Weboberfläche startet mit demselben Paket ohne `--cli`. Zugangsdaten
gehören weder in die Inspector-Konfiguration noch in dieses Repository.

## Conformance ist nicht Contract Testing

Das offizielle Paket `@modelcontextprotocol/conformance` prüft SDKs und
Protokolladapter gegen festgelegte Szenarien. Diese Szenarien erwarten eine
spezielle Referenzoberfläche. Ein Fachserver muss deshalb nicht die gesamte
Suite implementieren. Seine verpflichtenden Release-Gates sind die
projektspezifischen pytest-Contracts und der Inspector-Smoke-Test.
