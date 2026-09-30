# Begleitmaterial zu „n8n & MCP Engineering“

Lokal ausführbare Beispiele und Labore zu den beiden Bänden von Patrick Eiler:

- **Band 1: n8n, MCP und Python Engineering** – Kapitel 1–24, Ordner `code/ch01` bis `code/ch24`
- **Band 2: KI-Agenten, RAG und Produktionsbetrieb** – Kapitel 25–45, Ordner `code/ch25` bis `code/ch45`

Jedes Kapitel hat einen eigenen Ordner mit einer `README.md`. Sie nennt Voraussetzungen, Start- und
Prüfschritte sowie einen Lauf von Hand.

## Den passenden Stand holen

Jeder Band verweist auf einen festen Stand dieses Repositorys. Er trägt einen Tag:

```bash
git clone https://github.com/eiler-partner/n8n-mcp-buchbeispiele.git
cd n8n-mcp-buchbeispiele
git checkout band1-v1.0   # Stand zu Band 1
git checkout band2-v1.0   # Stand zu Band 2 (enthält auch alle Labore von Band 1)
```

Der Zweig `main` kann spätere Korrekturen enthalten, etwa Errata oder Anpassungen an neue Versionen von n8n.
Wenn Sie genau das Verhalten aus dem Buch nachvollziehen möchten, arbeiten Sie mit dem Tag Ihres Bandes.

## Voraussetzungen

- Docker Desktop mit Docker Compose v2
- Python 3.12 oder neuer, dazu `uv`
- `git` und `make`
- Node.js ab Version 22.19 für den MCP Inspector (Band 1 ab Kapitel 17)
- optional Ollama mit einem bereits installierten Modell (`qwen3:14b`, für Embeddings `all-minilm:latest`)

Kein Pflichtlabor braucht einen kostenpflichtigen API-Schlüssel. Die Skripte laden keine Modelle herunter.

Geprüfter Stand: n8n 2.40.7, MCP-Protokollrevision 2026-07-28, Python-SDK `mcp` 2.2.0,
Docker 29.8.1, Python 3.12.11, macOS 26.7 auf Apple Silicon (September 2026).

## Befehle

Alle Befehle rufen Sie im Wurzelverzeichnis dieses Repositorys auf. `make` ohne Ziel zeigt eine Übersicht.

```bash
make chNN-verify    # schnelle Tests ohne Docker, z. B. make ch25-verify
make chNN-live      # Docker-/n8n-Labor, wo das Kapitel eines hat
make chNN-ollama    # Band 2: optionaler Lauf mit einem installierten Ollama-Modell
make chNN-down      # Band 2: Container des Kapitels stoppen
make verify-all     # alle Offline-Prüfungen von Band 1
make verify-band2   # alle Offline-Prüfungen von Band 2
```

Einzelne Kapitel von Band 1 haben zusätzliche Ziele. Die Kapitel und die jeweilige `README.md` nennen sie.

Die Labore sind unabhängig voneinander. Starten Sie trotzdem immer nur ein Docker-Labor und beenden Sie es,
bevor Sie das nächste starten. Einige Labore aus Band 1 nutzen dieselben Ports, etwa 5678 für n8n.

## Datierte Laborberichte

Unter `code/chNN/reports/` liegen die datierten Berichte der Prüfläufe, auf die sich die Bücher beziehen. Sie
enthalten nur synthetische Daten, Hashes, Modell-Digests und Messwerte. Ein eigener Live-Lauf überschreibt diese
Dateien in Ihrer Arbeitskopie. Mit `git diff` vergleichen Sie Ihren Lauf mit dem Buchstand, mit
`git checkout -- code/chNN/reports` stellen Sie ihn wieder her. Messwerte wie Laufzeiten schwanken von Lauf zu Lauf.

## Sicher ausprobieren

Alle Daten, Identitäten, Tokens und Dokumente in den Beispielen sind erfundene Lehrdaten. Dateien namens
`.env.example` enthalten nur lokale Beispielwerte. Legen Sie bei Bedarf eine eigene `.env` an, verwenden Sie für
echte Systeme andere Geheimnisse und committen Sie die `.env` nie.

Die Beispiele sind keine unverändert einsetzbare Produktionskonfiguration. Prüfen Sie vor einem echten Einsatz
vor allem Netzwerkfreigaben, Berechtigungen, Aufbewahrung und die Lizenzbedingungen der verwendeten Drittsoftware.

## Lizenz

Der Beispielcode und die Laboranleitungen in diesem Repository stehen unter der [MIT-Lizenz](LICENSE),
Copyright (c) 2026 Patrick Eiler. Sie dürfen sie in eigenen Projekten verwenden, verändern und weitergeben,
auch kommerziell, solange der Lizenzhinweis erhalten bleibt.

Der Text der Bücher gehört nicht zu diesem Repository und steht nicht unter der MIT-Lizenz. Eingesetzte Pakete,
Container-Images, Dienste und Standards behalten ihre eigenen Lizenzen und Nutzungsbedingungen, zum Beispiel die
Sustainable Use License von n8n.

## Fehler melden

Wenn ein Beispiel nicht wie im Buch beschrieben funktioniert, eröffnen Sie bitte ein Issue in diesem Repository.
Nennen Sie dabei Band, Kapitel, den verwendeten Tag und die Ausgabe des fehlgeschlagenen Befehls.
