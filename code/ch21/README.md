# Kapitel 21: Kontrollierter Recherche-Agent

Das Labor besitzt genau zwei lesende Werkzeuge: `search_catalog` und
`read_document`. Das Modell darf Aufrufe vorschlagen. Der Python-Controller
erzwingt Allowlist, Pydantic-Schemas, Schritt- und Zeitbudget,
Wiederholungserkennung, Ergebnisgroesse und belegte Endantworten.

## Schnelle Tests

```bash
uv sync --dev
uv run pytest -m "not live"
```

## Lokaler Lauf mit Ollama

```bash
ollama serve
ollama pull qwen3:14b
cp .env.example .env
uv run research-agent "Welche Kontrollen verlangt der MCP-Toolvertrag?"
```

## API fuer n8n

```bash
docker compose up -d --build --wait
curl -s http://127.0.0.1:8030/research \
  -H 'Content-Type: application/json' \
  --data-binary '{"question":"Welche Kontrollen verlangt der MCP-Toolvertrag?"}'
```

Die Antwort muss `"status":"completed"` enthalten. `OLLAMA_HOST` aus `.env` gilt nur
fuer Aufrufe auf dem Mac; der Container nutzt `CONTAINER_OLLAMA_HOST`
(Standard `host.docker.internal`).

Importieren Sie danach `n8n/controlled-research.json`. Der Workflow ruft nur
den lesenden Recherche-Endpunkt auf. Eine nachgelagerte schreibende Aktion
wird bewusst nicht in denselben Agenten aufgenommen. Falls sie als n8n-Tool
ergänzt wird, muss sie im Tools Panel des AI Agent mit einer Human-Review-Stufe
versehen werden. Der Reviewer soll mindestens `$tool.name` und
`$tool.parameters` sehen.

## Cloud-Provider

`MODEL_PROVIDER=openai` beziehungsweise `anthropic` sowie API-Key und Modell-ID
aktivieren die jeweiligen offiziellen SDKs. Ohne die explizite Konfiguration
werden keine Cloud-Daten versendet. Modell-IDs sind absichtlich nicht im Code
festgeschrieben.
