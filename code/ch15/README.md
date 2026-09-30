# Kapitel 15: MCP-Primitives-Labor

Eigenständiger, synthetischer Compliance-Dienst. Das offizielle Python-SDK
stellt Resource, Tool, Prompt, Completion und die Form-Elicitation bereit.
Der moderne Form-Pfad läuft als echter MCP-Aufruf über die SDK-interne
MRTR-Abwicklung. Der URL-Modus ist bewusst eine **lokale Wire-Simulation**:
`https://consent.example.invalid` wird nie aufgerufen, und es gibt keine
Anmeldedaten oder echte externe Freigabe. `accept` bedeutet nur Zustimmung
zur Navigation, nicht den erfolgreichen Abschluss eines externen Vorgangs.

## Prüfen

```bash
UV_CACHE_DIR=/tmp/buch-ch15-uv-cache uv run --frozen pytest -q
docker compose run --build --rm primitives-lab
```

Die Tests lesen Resource- und Prompt-Ergebnisse, prüfen JSON-Schemas,
Completion, alle drei Form-Aktionen sowie die URL-Sequenz mit neuer
JSON-RPC-ID. `docker compose run --rm` hinterlässt keinen laufenden
Laborcontainer; `network_mode: none` verhindert ausgehende Verbindungen.

Der Dienst kann für einen lokalen MCP-Host auch über `stdio` gestartet
werden: `uv run --frozen python -m mcp_primitives_lab.server`.

Getesteter Stand: MCP `2026-07-28`, Python-SDK `mcp==2.2.0`, Python 3.12.
Die URL-Sequenz ist kein behaupteter Live-Server-Trace. Ein echter
OAuth-/Drittanbieterfluss ist absichtlich nicht Teil dieses Kapitels.
