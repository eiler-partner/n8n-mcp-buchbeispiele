# Kapitel 25: Providerabstraktion und Modellauswahl

Dieses eigenständige Labor zeigt eine **Auswahlregel**, keinen Benchmark realer Modelle. Die drei Profile `sparsam-lokal`, `praezise-lokal` und `extern-variabel` sind künstliche Fixtures. Latenz in Millisekunden und `synthetic_cost_units` sind erfundene Lehrwerte. Es gibt keine Modell-Downloads und keine API-Schlüssel im Pflichtpfad.

## Schneller Prüflauf

Aus dem Wurzelverzeichnis des Begleitmaterials:

```sh
make ch25-verify   # schnelle Vertragstests ohne Docker
make ch25-live     # baut und startet Dienst und n8n, dann verify_live.py
make ch25-down     # Container des Kapitels stoppen
```

Im Kapitelordner `code/ch25` gelten gleichwertig `make test`, `make live` und `make down`. `make ch25-live` führt `docker compose up -d --build --wait` und danach `python3 verify_live.py` aus. `make ch25-down` stoppt und entfernt nur die Container und das Netzwerk dieses Labors; das Datenbankvolume bleibt erhalten. Frisch beginnen kann man mit einem neuen Compose-Projektnamen, ohne vorhandene Daten zu löschen.

Der Python-Dienst liegt auf `http://127.0.0.1:8125`, n8n auf `http://127.0.0.1:15725`. Das Kapitel-Workflow empfängt einen `POST` an `/webhook/ch25-select`, ruft den Auswahlvertrag auf und zeigt die Entscheidung samt synthetischem, ausgewähltem Fixture-Aufruf. Beispiel:

```sh
curl -sS -X POST http://127.0.0.1:15725/webhook/ch25-select \
  -H 'Content-Type: application/json' \
  --data '{"scenario":"lokal-qualitaet","case_id":"e01"}' | python3 -m json.tool
```

Erwartet: `selected=praezise-lokal`, `fixture_invocation.observed=hinweis`, `extern-variabel` ausgeschlossen mit `datenweg`. Mit `lokal-kosten` und `case_id=c01` gewinnt dagegen `sparsam-lokal`. Mit `failure_kind=timeout` wird nur auf einen Kandidaten gewechselt, der **dieselben harten Kriterien** erfüllt. `policy` und fehlende Fallback-Kandidaten führen zu einem Fehler.

Die n8n-Ausführung ist absichtlich ein einfacher Webhook → Auswahlvertrag → Antwort-Pfad. Sie führt **nicht** den n8n-`Model Selector`-Sub-Node aus: Dafür müssten echte Chat-Model-Nodes angehängt werden. Das Kapitel erläutert dessen Regelsemantik separat. Diese Grenze wird nicht als ausgeführter Test ausgegeben.

## Freiwilliger echter Ollama-Lauf

Für Leser freiwillig, für die redaktionelle Abnahme verpflichtend. Ollama läuft auf dem Host; ein installiertes Modell wird vorausgesetzt. Es wird nichts heruntergeladen:

```sh
make ch25-ollama
```

Im Kapitelordner entspricht das `make ollama`; das alte Ziel `make ollama-live` ist nur noch ein Alias dafür. Voreinstellung ist `qwen3:14b` auf `127.0.0.1:11434`. Für ein anderes Modell im Kapitelordner: `PYTHONPATH=src python3 -m ch25_lab.cli ollama-live --model NAME --output reports/ollama-observation.json`. Der Bericht enthält UTC-Zeit, Host, Ollama-Version, vollständigen Digest, Datensatz-Hash, Promptversion, Antworten und beobachtete Dauer. Automatisch wird nur das Ausgabeformat geprüft. Korrektheit und Latenz sind Momentaufnahmen, keine zugesicherte Modellleistung.

## Daten und Vertrag

- `data/cases.json`: zwölf synthetische Fälle (sechs einfache Klassifikationen, drei Tool-Fälle, drei Grenzfälle).
- `data/profiles.json`: drei unveränderliche Fixture-Profile.
- `data/scenarios.json`: Muss-Kriterien, Grenzen und vorab festgelegte Gewichte.
- `GET /report`: alle Entscheidungen mit Datensatz-Hash.
- `POST /choose`: `scenario`, optional `case_id` und `failure_kind`.

Zuerst werden Fähigkeiten, Datenweg, Kosten- und Latenzbudget geprüft. Nur zulässige Profile werden bewertet. Die Funktion prüft fehlende Messwerte und bricht sicher ab. Ein Fallback ist nur bei `timeout`, `transport` oder `rate_limit` möglich. Fach- und Policyfehler sind nicht retrybar.
