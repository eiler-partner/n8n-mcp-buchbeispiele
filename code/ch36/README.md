# Kapitel 36: RAG-Evaluation und Regression

Eigenständiges, synthetisches 2x2-Labor. Pflichtpfad: Python 3.11+ ohne
Modell-Download oder API-Schlüssel. Der Bericht prüft zwei Chunking-Varianten
(`short`, `wide`) gegen zwei Suchvarianten (`lexical`, `expanded`) auf denselben
zehn Fällen. `expanded` ist ein **festes Synonymwörterbuch**, kein Embedding.

Im Repository-Root:

```sh
make ch36-verify   # schnelle Tests ohne Docker
make ch36-live     # Docker-/n8n-Labor (baut, startet, prüft)
make ch36-ollama   # optional, siehe unten
make ch36-down     # Container des Kapitels stoppen
```

Im Kapitelordner gelten gleichwertig `make test`, `make live`, `make ollama`
und `make down`.

Für den reinen Fixture-Bericht ohne Docker (Zusatzziel nur im Kapitelordner,
dort `make report`):

```sh
make -C code/ch36 report
```

Berichte entstehen unter `reports/`. Sie enthalten Datum, Korpus-/Gold-Hashes,
Fälle, Treffer, Antwort-Fixture, Metriken und Gate-Gründe. Die Quelle der
„Antworten“ ist ein absichtlich naiver deterministischer Adapter: Er gibt die
Fakten des ersten Treffers als Sätze mit Beleg aus. Er ist **kein Sprachmodell**
und seine Werte sind keine Schätzung realer Modellqualität.

Der Live-Pfad startet nur `buch-ch36`, bindet n8n an `127.0.0.1:15736` und den
Python-Dienst an `127.0.0.1:8136`. Er testet beide sowie ein enges MCP-Tool-
Subset. Beispiel:

```sh
curl -sS -X POST http://127.0.0.1:15736/webhook/ch36-evaluation \
  -H 'Content-Type: application/json' \
  --data '{"action":"compare"}' | python3 -m json.tool
```

Der Webhook ist **nicht authentifiziert** und nur für Loopback bestimmt. Die
Rollen in `golden.json` sind feste Testdaten, keine Nutzeridentitäten. Eine
produktive Übernahme braucht Authentisierung und Autorisierung vor dem
Evaluator; Datensätze dürfen keine echten Geheimnisse enthalten.

Optional für Leser, bei der redaktionellen Mac-Abnahme ausgeführt:
`make ch36-ollama` (im Kapitelordner `make ollama`). Das Script verwendet
ausschließlich ein bereits installiertes `CH36_OLLAMA_MODEL` (Standard
`qwen3:14b`), lädt nichts herunter, speichert den vollen Digest und prüft nur die JSON-Form zweier Judge-Antworten.
Seine inhaltlichen Urteile werden als datierte Beobachtungen protokolliert,
nicht als Gate oder fest zugesagte Modellleistung.

Native n8n-Evaluationsfunktionen können ergänzend an einen eigenen Datensatz
angeschlossen werden: Evaluation Trigger für Testfälle, Evaluation Node / Set
Outputs für sichtbare Einzelergebnisse und Set Metrics für numerische Werte.
Der verpflichtende Bericht bleibt als versioniertes JSON unabhängig von
Edition, Daten-Tabellen und Cloud-Credentials.
