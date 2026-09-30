# Kapitel 23: Sicherheitsgrenzen und Prompt-Injection-Abwehr

Das Labor verwendet ausschließlich den synthetischen Canary-Wert aus
`.env.example`. Der verwundbare Pfad sendet ihn nur an einen lokalen
Capture-Dienst im Docker-Labornetz; veröffentlichte Ports sind fest an
`127.0.0.1` gebunden. Reale Geheimnisse und externe Ziele sind ausdrücklich
nicht Teil des Versuchs.

## Contract Tests

```bash
uv sync --dev
uv run pytest
```

Die Tests prüfen Tool-Allowlist, Manifest-Pinning gegen Rug Pulls,
Tenant-Trennung, Ziel- und Größenbegrenzung, Approval-Bindung,
`x-mcp-header`-Validierung, Audit-Redaktion und die n8n-Fixture.

## Lokaler Angriff und Abwehr

```bash
cp .env.example .env
docker compose up -d --build --wait
uv run ch23-demo --mode vulnerable
curl http://127.0.0.1:8024/health
uv run ch23-demo --mode hardened
docker compose down
```

Der erste Lauf muss `executed: true` und anschließend genau einen lokalen
Capture melden. Der zweite Lauf muss `executed: false` liefern. Die
Grundcodes lauten `UNTRUSTED_SOURCE_TO_EXTERNAL_SINK` und
`APPROVAL_MISSING_OR_STALE`.

## n8n als zusätzlicher Integrationsschritt

```bash
docker compose --profile n8n up -d --build --wait
```

Danach `n8n/deterministic-boundary.json` importieren und einmal manuell
ausführen. Der Zweig **Blocked and Audited** muss erreicht werden. Das
Beispiel setzt `NODES_EXCLUDE` für Execute Command, Local File Trigger sowie
Read/Write Files. Die Variable ersetzt die n8n-Standardliste; deshalb steht
der standardmäßig gesperrte Local File Trigger ausdrücklich darin. Das Beispiel
bindet n8n ausschließlich an Loopback.

Ein Guardrails Node kann vor die Grenze geschaltet werden, um beispielsweise
Jailbreaks, URLs oder Secret-Muster zusätzlich zu erkennen. Er ersetzt die
deterministische Freigabe nicht: Klassifikatoren können irren und kennen weder
den gültigen Tool-Vertrag noch die konkrete menschliche Freigabe.

## Optionale Modelltests

Ein lokales Ollama-Modell oder ein Cloud-Modell darf statt der skripteten
Planungs-Fixture Vorschläge erzeugen. Diese Runde ist explorativ. Die
Sicherheitsabnahme bleibt modellunabhängig und muss auch ohne API-Schlüssel
vollständig bestehen.
