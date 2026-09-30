# Kapitel 26: Prompts, strukturierte Ausgaben und Modelltests

Eigenständiges Labor mit acht **synthetischen** Terminanfragen, zwei Promptversionen und deterministischen Fixture-Antworten. Es bucht oder storniert nichts. Der Pflichtpfad braucht weder Modell-Download noch bezahlten API-Schlüssel.

## Schnellstart

Voraussetzungen: Python 3.12+, `uv`, Docker Desktop oder Docker Engine mit Compose.

Aus dem Wurzelverzeichnis des Begleitmaterials:

```sh
make ch26-verify   # Vertragstests ohne Docker
make ch26-live     # baut und startet das Labor, dann verify_live.py
make ch26-down     # Container des Kapitels stoppen
```

Im Kapitelordner `code/ch26` gelten gleichwertig `make test`, `make live` und `make down`. `make ch26-live` führt `docker compose up -d --build --wait` und danach `UV_CACHE_DIR=/tmp/buch-ch26-uv-cache uv run --locked python verify_live.py` aus. `make ch26-down` entfernt nur die Kapitel-26-Container und das Netzwerk; das eigene Datenbankvolume bleibt erhalten. Die Ports sind `8126` für den Python-Vertrag und `15726` für n8n.

Der n8n-Webhook ist `POST http://127.0.0.1:15726/webhook/ch26-extract`. Beispiel:

```sh
curl -sS -X POST http://127.0.0.1:15726/webhook/ch26-extract \
  -H 'Content-Type: application/json' \
  --data '{"case_id":"c05","variant":"baseline"}' | python3 -m json.tool
```

Erwartet: `contract_pass=false`, `golden_pass=false`, `exact_match=false`, `error_class=schema`. Mit `candidate` bestehen Vertrag und Golden-Ergebnis. `c08` in der Baseline ist **schema- und fachvertragsgültig**, aber weicht von der Sollantwort ab (`golden_mismatch`). Das illustriert, warum JSON-Schema-Validierung allein keine Qualitätsmessung ist.

`uv run --locked ch26-lab report` zeigt beide Fixture-Suiten, die Hashes von Prompt, Schema und Datensatz sowie das Release-Gate. Baseline: 6/8 Vertragsfälle, 5/8 Golden-Fälle (feldweise wie exakt). Kandidat: 8/8 in beiden Schichten. Diese Werte sind künstliche Testdaten, kein Modellbenchmark.

Das Release-Gate (`release_ready`) verlangt für alle Kandidatenfälle Vertrag und feldweisen Golden-Vergleich (`golden_pass`): `intent`, `date` und `needs_review` exakt wie die Sollantwort, `evidence` als wörtlicher Ausschnitt des Eingabetexts. Ein anderer, aber wörtlicher Beleg besteht also. Der exakte Vergleich des ganzen Objekts steht zusätzlich als `exact_match` im Ergebnis und als `exact_match_count` im Bericht; das Gate nutzt ihn nicht.

## Echter Ollama-Lauf (für Leser freiwillig)

Ein bereits installiertes Ollama-Modell auf dem Host vorausgesetzt:

```sh
make ch26-ollama
```

Im Kapitelordner entspricht das `make ollama`; das alte Ziel `make ollama-live` ist nur noch ein Alias dafür. Voreinstellung: `qwen3:14b` auf `127.0.0.1:11434`. Ein anderes installiertes Modell kann im Kapitelordner mit `uv run --locked ch26-lab ollama-live --model NAME --output reports/ollama-observation.json` gewählt werden. Es findet kein Download statt. Der Bericht enthält UTC-Zeit, Host, vollständigen Modell-Digest aus `/api/tags`, Prompt-/Schema-/Datensatz-Hash und Einzelantworten. Der Live-Lauf prüft den Ausgabe- und Fachvertrag; die Golden-Treffer und Dauern sind nur datierte Beobachtungen. Bei Vertragsfehlern bleibt der Bericht erhalten und der Befehl beendet sich mit Fehlerstatus.

OpenAI- und Anthropic-APIs sind konzeptionelle optionale Vergleichspfade; das Labor führt keine Cloud-Aufrufe aus und speichert keine Zugangsdaten. Bei einem späteren Cloud-Lauf müssen Modell-ID, API-Version, Datenweg und Kosten gesondert geprüft werden.

## Was die drei Prüfschichten leisten

1. JSON-Syntax und Schema: vollständige Felder, Enum, Typen, Datum und keine zusätzlichen Schlüssel.
2. Fachliche Invarianten: Belegausschnitt muss in der Eingabe stehen (`semantic_evidence`). Das Datum muss als Zeichenkette wörtlich in der Eingabe stehen (`semantic_date`); das genügt, weil alle Falltexte ISO-Daten enthalten. Eine Eingabe wie „am 14. Oktober“ müsste vorher normalisiert werden. Eine reine Frage trägt weder Datum noch Review (`semantic_information`), eine Aktion verlangt genau dann Review, wenn das Datum fehlt (`semantic_review`).
3. Golden-Vergleich, feldweise: Kernfelder exakt, Beleg als wörtlicher Ausschnitt der Eingabe. Ein falsches Kernfeld bleibt als Qualitätsfehler sichtbar (`golden_mismatch`). Der exakte Objektvergleich (`exact_match`) ist nur zusätzliche Information.

n8n ruft den Python-Vertrag auf und zeigt die Resultate im Ausführungsprotokoll. Der n8n-Sub-Node *Structured Output Parser* und das eingebaute Evaluationsfeature werden im Buch eingeordnet, sind jedoch nicht Teil dieses ausgeführten Pflichtworkflows. Damit bleibt der lokale Test auch ohne Provider-Credentials und unabhängig von n8n-Editionsmerkmalen ausführbar.
