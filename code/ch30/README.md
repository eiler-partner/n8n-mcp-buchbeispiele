# Kapitel 30 – Mini-RAG und Informationslebenszyklus

Eigenständiges Lehrlabor mit ausschließlich synthetischen Richtlinien. Python 3.12 und für den n8n-Lauf Docker Desktop/Compose genügen; weder API-Schlüssel noch Modell-Download sind nötig. Keine früheren Kapitelcontainer werden verwendet.

## Schnellstart

Vom Repository-Wurzelverzeichnis:

```sh
make ch30-verify
make ch30-live
make ch30-down
```

Im Kapitelordner `code/ch30` gelten gleichwertig `make test`, `make live` und `make down`.

`make ch30-live` startet nur `buch-ch30` und schreibt `code/ch30/reports/live-observation.json`. Der n8n-Webhook liegt auf `http://127.0.0.1:15730/webhook/ch30-rag`, der Python-Dienst auf Port 8130. Beispiel:

```sh
curl -sS -X POST http://127.0.0.1:15730/webhook/ch30-rag \
  -H 'Content-Type: application/json' \
  --data '{"question_tag":"urlaub","tenant":"werk","role":"employee","as_of":"2026-09-29"}'
```

Die drei Strategien im Direktvergleich:

```sh
curl -sS -X POST http://127.0.0.1:8130/compare \
  -H 'Content-Type: application/json' \
  --data '{"question_tag":"urlaub","tenant":"werk","role":"employee","as_of":"2026-09-29"}'
```

Die Basislinie ist **eine feste fiktive Modellantwort** ohne Beleg. `full_context` erhält sämtliche zum Stichtag gültigen und für die Rolle sichtbaren Quelltexte; `rag` wählt daraus nur den passenden Fragetyp. Beide Antworten sind deterministische Extraktionen, **keine LLM-Generierung**. Der Vergleich misst weder Trefferqualität realer Retriever noch Modellqualität, Tokenkosten oder Latenz. Das Szenario verdeutlicht allein die Vertragsgrenzen. Die Fälle `gehalt` als `employee` und `unbekannt` müssen `withheld` liefern.

## MCP-Ressourcenspur

`PYTHONPATH=src CH30_TENANT=werk CH30_ROLE=employee python3.12 -m ch30_lab.mcp_stdio` startet einen kleinen stdio-Adapter für `resources/list` und `resources/read` nach dem Resource-Nachrichtenschema der Version `2026-07-28`. `verify_live.py` sendet echte JSON-RPC-Zeilen an diesen Prozess und prüft Listen, Lesen und den verweigerten HR-Zugriff. Es ist ein **Resource-Lehrsubset**, kein produktionsreifer, vollständiger MCP-Host-Integrationsserver. Das Labor verwendet lokale Prozessumgebungswerte für den Scope, keine verifizierte Nutzeridentität; ein echtes Deployment braucht Authentifizierung, Autorisierung pro Anfrage und Tests mit einem unabhängigen MCP-Client.

## Daten und Grenzen

`data/sources.json` enthält aktuelle, ältere, gelöschte, fremde und HR-interne Fassungen. Ein `chunk_id` ist hier ein von Hand kuratierter kurzer Textabschnitt. Er ist keine Demonstration eines allgemeinen Chunkers. Gültigkeitsgrenzen sind halboffen: `valid_from <= as_of < valid_until`. Bei Löschung werden Datensätze aus diesem Lehrkorpus nicht physisch entfernt; das Flag verhindert nur Abruf. Eine echte Löschgarantie umfasst Quellsystem, Index, Cache, Backups und Audit-Aufbewahrung und wird hier nicht behauptet.

Die Rolle im HTTP-Body ist absichtlich unbeglaubigt. Die n8n- und Python-Endpunkte binden ausschließlich an Loopback, und die Kennwörter in `compose.yaml` sind Lehrwerte. Keine realen Personal- oder Unternehmensdaten eingeben.

## Aufräumen

```sh
make ch30-down
```

Die Kapitel-30-Container und das Netzwerk werden gestoppt/entfernt; das eigene Postgres-Volume bleibt für eine Wiederaufnahme erhalten. Für ein frisches Labor kann das Volume nach bewusster Sicherungsentscheidung separat entfernt werden; dieser Schritt ist nicht Teil von `make ch30-down`.
