# Kapitel 28: Orchestrierung nur bei messbarem Nutzen

Dieses eigenständige Labor stellt eine einfache deterministische Lösung einem n8n-Pfad mit **Router → Worker → Reviewer** gegenüber. Die Rollen sind synthetische Funktionen mit strengen Übergabeverträgen, **keine drei realen LLM-Agenten**. Das Labor misst nicht Modellqualität; es macht Kontext-, Fehler- und Stufenkosten einer zusätzlichen Rolle sichtbar. Der Pflichtpfad braucht weder API-Schlüssel noch Modell-Download.

## Voraussetzungen

- Python 3.12 oder neuer; keine Runtime-Pakete außerhalb der Standardbibliothek.
- Für `make ch28-live`: Docker Desktop/Compose. Das Kapitel bindet seine Ports nur an Loopback: Python `8128`, n8n `15728`.
- Compose-Images: `python:3.12-slim`, `postgres:17-alpine`, `n8nio/n8n:2.40.7`. Nur eigene Kapitel-28-Container und ein eigenes n8n-Volume.
- Laborpasswörter und offener Webhook sind ausschließlich für die lokale Testumgebung. Keine echte Mandanten-Authentifizierung.

## Schnelle, reproduzierbare Abnahme

Die Laborbefehle laufen aus dem Wurzelverzeichnis des Begleitmaterials. Im Kapitelordner `code/ch28` gelten gleichwertig `make test`, `make live`, `make ollama` und `make down`. Den Vergleichsbericht erzeugt dort zusätzlich `make report`.

```sh
make ch28-verify
make -C code/ch28 report
```

Einundzwanzig Tests laufen. Sechzehn Unit- und Negativtests prüfen die acht Fälle und Manipulationen von Mandant, Route, Kontext, Trace, Budget, Quelle und Antwort. Fünf weitere prüfen die Struktur des n8n-Workflows: eindeutige IDs, vollständige Verbindungen, unveränderte Node-Typen, den Fehlerausgang jeder Stufe und den Testschalter `tamper`. `reports/comparison.json` enthält Datensatz- und Wissens-Hash, Einzelresultate und Architekturentscheidung. Erwartet: Basislinie 8/8, Mehrstufenweg 8/8, Stufenzahl 8 gegen 24, `decision=baseline`. Die zusätzliche Rolle wird also für **diese** feste Aufgabe nicht empfohlen. Das ist keine allgemeine Aussage gegen Agenten.

## Echter n8n-Pfad

```sh
make ch28-live
```

Compose baut den Python-Dienst, startet eine nur für dieses Kapitel bestimmte PostgreSQL-/n8n-Instanz, importiert und publiziert den Workflow. `verify_live.py` ruft **beide** Webhooks für alle acht Fälle auf. Danach schickt es drei negative Übergaben über **denselben** Webhook `ch28-multi`:

| Manipulation | Aufruf | erwartet |
| --- | --- | --- |
| fremder Mandant | Body `{"case_id":"c01","tenant_id":"other"}` | 422, `rejected_by=Router`, `tenant_mismatch` |
| veränderter Kontext | `?tamper=context` | 422, `rejected_by=Specialist Worker`, `context_mismatch` |
| erfundene Antwort | `?tamper=answer` | 422, `rejected_by=Contract Reviewer`, `worker_result_mismatch` |

Die übrigen vier Manipulationen (Route, Trace, Budget, Quelle) prüft nur `make ch28-verify`. Der datierte Bericht steht unter `reports/live-observation.json`.

So kommen die Manipulationen in den n8n-Pfad: Der Query-Parameter `tamper` ist ein **Testschalter nur dieses Lehr-Workflows**. Bei `tamper=context` ersetzt der Node „Specialist Worker“ vor dem Aufruf von `/work` den Kontextausschnitt durch `fremder Kontext`. Bei `tamper=answer` ersetzt der Node „Contract Reviewer“ vor dem Aufruf von `/review` die Worker-Antwort durch `erfundene Antwort`. Ohne den Parameter reichen beide Nodes die Hülle unverändert weiter. Ein produktiver Workflow darf Übergaben nicht auf Zuruf des Aufrufers verändern.

Weist eine Stufe ab, greift ihre Node-Einstellung *On Error: Continue (using error output)*. Der Fehlerausgang führt zum Node „Return Stage Rejection“. Er antwortet mit HTTP 422, dem Namen der Stufe in `rejected_by` und der Fehlermeldung des HTTP-Request-Nodes in `detail`. Diese Meldung enthält die Antwort des Python-Dienstes und damit den Fehlercode. Der Basislinien-Webhook hat keinen solchen Fehlerausgang.

```sh
curl -sS -X POST 'http://127.0.0.1:15728/webhook/ch28-multi?tamper=context' \
  -H 'Content-Type: application/json' \
  --data '{"case_id":"c01","tenant_id":"lab"}'
```

Erwartet (HTTP 422): `{"rejected_by":"Specialist Worker","detail":"422 - \"{\\\"error\\\": \\\"context_mismatch\\\"}\""}`.

Vor den Prüfungen wartet `verify_live.py` höchstens 90 Sekunden, bis n8n die importierte Fassung ausführt. Direkt nach dem Start meldet n8n die Webhooks teils noch als unbekannt. Lag im Volume schon eine ältere Fassung dieses Workflows, führt n8n diese nach dem Start noch einige Sekunden lang aus; eine abgewiesene Übergabe endet dort nur mit HTTP 500 („Error in workflow“), ohne Stufe und Fehlercode.

Ein manueller Gegenvergleich:

```sh
curl -sS -X POST http://127.0.0.1:15728/webhook/ch28-baseline \
  -H 'Content-Type: application/json' \
  --data '{"case_id":"c03","tenant_id":"lab"}'
curl -sS -X POST http://127.0.0.1:15728/webhook/ch28-multi \
  -H 'Content-Type: application/json' \
  --data '{"case_id":"c03","tenant_id":"lab"}'
```

Beide Antworten sollen `route=privacy` und dieselbe synthetische Fachantwort liefern. Der Mehrstufenweg enthält zusätzlich `trace_id` und gezählte Kontextbytes.

## Optionaler lokaler Modellblick

```sh
make ch28-ollama
```

Das alte Ziel `make ollama-live` ist nur noch ein Alias für `make ollama` im Kapitelordner. Der Befehl verwendet ein **bereits installiertes** `qwen3:14b` über Ollama. Er lädt kein Modell herunter, zeichnet vollen Digest, Zeit, Host und vier Routingantworten in `reports/ollama-observation.json` auf. Diese Beobachtung ist kein Benchmark und kein Bestandteil des deterministischen Leser-Gates. Cloud-Provider könnten denselben Routingvertrag freiwillig prüfen; sie sind nicht implementiert und nicht nötig.

## Grenzen und Aufräumen

Der Reviewer prüft Schema, Herkunft und feste Antworten. Er ist keine unabhängige Wahrheitsinstanz und kein menschlicher Freigabeprozess. Alle Daten sind synthetisch. Die A2A-Spezifikation wird im Kapitel eingeordnet; dieser Workflow ist **kein A2A-Server**. Externe Tools, echte Parallelität, Authentifizierung und kostengebundene LLM-Aufrufe benötigen zusätzliche Arbeit und gehören nicht zur Abnahme.

```sh
make ch28-down
```

Dies stoppt und entfernt nur Kapitel-28-Container und Netzwerk; das eigene PostgreSQL-Volume bleibt erhalten. Keine globalen Docker-Aufräumbefehle verwenden.
