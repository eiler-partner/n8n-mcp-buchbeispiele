# Kapitel 12: Providerneutrale Modelladapter

Das Labor fuehrt dieselbe Rechnungsdatenextraktion ueber OpenAI, Anthropic
oder Ollama aus. Die Fachlogik kennt nur `ExtractionRequest` und
`ExtractionEnvelope`; Modellnamen und Zugangsdaten bleiben Konfiguration.

## Schnelle Vertragstests

```bash
uv sync --dev
uv run pytest -m "not live"
```

## Lokales Ollama auf Apple Silicon

Ollama sollte auf macOS nativ laufen, damit Metal/GPU genutzt wird:

```bash
ollama serve
ollama pull qwen3:14b
cp .env.example .env
uv run model-lab examples/invoice.txt
```

Die lokale API benoetigt keinen API-Schluessel. Das Modell ist fuer das Labor
konfiguriert und kann spaeter ohne Codeaenderung ersetzt werden.

## HTTP-Schnittstelle fuer n8n

```bash
docker compose up -d --build --wait
curl -s http://127.0.0.1:8020/extract \
  -H 'Content-Type: application/json' \
  --data-binary '{"document_id":"demo","text":"Rechnung R-1, EUR 12,00"}'
```

Der Container erreicht natives Ollama ueber `host.docker.internal`. `OLLAMA_HOST`
aus `.env` gilt nur fuer Aufrufe auf dem Mac; fuer den Container gibt es die
eigene Variable `CONTAINER_OLLAMA_HOST`. Das
optionale Profil `cpu-local` startet Ollama in Docker ohne Apple-GPU:

```bash
CONTAINER_OLLAMA_HOST=http://ollama-cpu:11434 docker compose --profile cpu-local up -d
docker compose --profile cpu-local exec ollama-cpu ollama pull qwen3:14b
```

Dieses Profil ist fuer Linux/CI oder bewusste CPU-Tests gedacht, nicht als
leistungsfaehiger Standard auf dem Mac.

## Optionale Cloud- und Live-Tests

Modell-IDs und Schluessel werden nur lokal in `.env` oder der Shell gesetzt.
Live-Tests verursachen gegebenenfalls Kosten und senden den Testtext an den
konfigurierten Provider:

```bash
RUN_LIVE_MODEL_TESTS=1 uv run pytest -m live
```

Ohne die explizite Variable werden alle Live-Tests uebersprungen. Fehler bei
Authentifizierung, Schema, Refusal oder Policy loesen keinen stillen Wechsel
zu einem anderen Provider aus.
