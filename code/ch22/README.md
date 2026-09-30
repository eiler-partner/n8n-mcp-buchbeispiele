# Kapitel 22: n8n als MCP-Client und MCP-Server

Das Labor trennt zwei Richtungen und drei Oberflächen: Das n8n MCP Client
Tool konsumiert einen externen Python-Server; der MCP Server Trigger bietet
genau einen kontrollierten Workflow als Tool an. Der instanzweite MCP-Zugang
ist ein zusätzlicher, bewusst manueller Integrationsschritt.

## Schnelle Contract Tests

```bash
uv sync --dev
uv run pytest
```

Die Tests prüfen die geschlossene Tool-Allowlist, den strukturierten
Python-SDK-v2-Server, das Protokollmessformat, die beiden n8n-Workflowexporte,
den Reverse-Proxy-Vertrag und die festgelegte n8n-Version.

## Docker-Labor

```bash
cp .env.example .env
docker compose up -d --build --wait
```

n8n ist danach ausschließlich auf `http://127.0.0.1:5678` erreichbar. Die
Python-MCP-Endpunkte laufen auf:

- Streamable HTTP: `http://127.0.0.1:8022/mcp`
- Legacy-SSE: `http://127.0.0.1:8023/sse`

Der Streamable-HTTP-Vertrag lässt sich ohne n8n prüfen:

```bash
uv run ch22-probe \
  --url http://127.0.0.1:8022/mcp \
  --token chapter-22-local-token-change-me \
  --allow catalog_lookup \
  --output reports/python-http.json

uv run ch22-probe \
  --transport sse \
  --url http://127.0.0.1:8023/sse \
  --token chapter-22-local-token-change-me \
  --allow catalog_lookup \
  --output reports/python-sse.json
```

`maintenance_reset` ist eine negative Fixture. Der Server veröffentlicht sie,
damit der n8n-Filter beweisen muss, dass nur `catalog_lookup` beim Agenten
ankommt. Das Werkzeug selbst verweigert zusätzlich jede Ausführung.

## n8n als Client

1. `n8n/client-agent.json` importieren.
2. Eine Bearer-Credential `CH22 MCP Bearer` mit dem Token aus `.env` anlegen.
3. Eine Ollama-Credential mit `http://host.docker.internal:11434` anlegen und
   `qwen3:14b` bereitstellen.
4. In **Selected MCP Catalog Tool** kontrollieren: Transport
   **HTTP Streamable**, Modus **Selected**, einziges Tool
   `catalog_lookup`.
5. Den Chat mit „Suche nach n8n“ ausführen. Die Antwort muss `N8N-022`
   enthalten; `maintenance_reset` darf dem Agenten nicht angeboten werden.
6. Für die SSE-Kompatibilitätsrunde Endpoint auf
   `http://mcp-sse:8023/sse` und Transport auf **SSE** umstellen. Danach zur
   produktiven Vorlage mit Streamable HTTP zurückkehren.

## n8n als Server

1. Zuerst `n8n/catalog-tool-workflow.json`, danach
   `n8n/server-trigger.json` importieren.
2. Eine separate Bearer-Credential `CH22 n8n MCP Bearer` anlegen.
3. Den Katalog-Subworkflow veröffentlichen. Danach zuerst **Listen for Test
   Event** am Serverworkflow verwenden und die angezeigte Test-URL mit
   Inspector oder einem Python-Client prüfen.
4. Danach den Serverworkflow veröffentlichen und ausschließlich die Produktions-URL in der
   dauerhaften Clientkonfiguration hinterlegen.
5. `tools/list` muss exakt `catalog_lookup` liefern. Ein falscher oder
   fehlender Token muss vor Discovery scheitern.

Die URL wird aus der n8n-Oberfläche kopiert; sie wird nicht aus dem
Workflowpfad geraten. Test- und Produktionsregistrierung unterscheiden sich.

## Instanzweites MCP als zusätzlicher Schritt

Unter **Settings > Instance-level MCP** den Zugang aktivieren, OAuth wählen,
nur lesende Suchberechtigungen erteilen und genau den veröffentlichten
Testworkflow freigeben. Nach `search_workflows` und einer kontrollierten
Ausführung den Client unter **Connected clients** widerrufen. Schreibende
Workflow- oder Data-Table-Scopes gehören nicht in diesen Basistest.

## Queue-Profil

```bash
docker compose --profile queue up -d --build --wait
```

Das Profil startet Redis und einen Worker. Es ist kein Beweis für beliebige
Ingress-Topologien: Die mit der getesteten n8n-Version beobachtete
MCP-Sitzungs- und Webhook-Verteilung wird in einem Ergebnisbericht festgehalten.
Bis diese Prüfung für die konkrete Version bestanden ist, werden alle
`/mcp*`-Anfragen wie in der Node-Dokumentation zu einer dedizierten
Webhook-Replik geleitet.
