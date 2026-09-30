# Kapitel 24: Vom Workflow zum MCP-Dienst

Dieses Labor verbindet n8n 2.40.7, einen Python-MCP-Server auf Basis des
SDK 2.2.0, PostgreSQL, eine deterministische OpenAI-kompatible Modell-Fixture
und Jaeger 2.21.0. Alle veröffentlichten Ports sind an `127.0.0.1` gebunden.
Die Werte in `.env.example` sind ausschließlich lokale Laborschlüssel.

## Ein Befehl für Start und Abnahme

```bash
make verify
```

Der Befehl baut die Images, importiert und aktiviert drei n8n-Workflows,
startet den Stack, führt Unit-, Contract-, MCP- und Security-Tests aus und
prüft anschließend den kompletten Schreibpfad. Der Bericht landet unter
`reports/verification.json`.

Die Dienste bleiben zur Inspektion aktiv:

- n8n: <http://127.0.0.1:5678>
- Jaeger: <http://127.0.0.1:16686>
- Python-API: <http://127.0.0.1:8024/health>
- MCP: `http://127.0.0.1:8025/mcp`

Aufräumen:

```bash
make down
```

## Sichtbare menschliche Freigabe

Nach einem erzeugten Publikationsvorschlag kann das lokale n8n-Formular unter
`http://127.0.0.1:5678/form/ch24-review` geöffnet werden. Das Formular ist nur
die Bedienoberfläche: Die Python-Grenze bindet Reviewer, Vorschlags-Digest und
Ablaufzeit zusätzlich mit HMAC. Ohne gültige gebundene Freigabe bleibt der
Executor gesperrt.

## Modellvarianten

Die Abnahme verwendet die reproduzierbare Fixture `ch24-fixture`. Im Workflow
**CH24 - MCP document agent** kann die OpenAI-kompatible Basis-URL anschließend
optional auf Ollama, vLLM oder einen Cloud-Anbieter umgestellt werden. Solche
Modellrunden sind explorativ und ersetzen die deterministischen Tests nicht.
