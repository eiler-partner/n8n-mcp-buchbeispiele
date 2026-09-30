# Kapitel 43: eigenständiger Wissensassistent

Synthetisches Prozesshandbuch, signierte Lehridentität, ACL vor Hybrid-Ranking,
extraktive Antwort mit nachgeprüftem Beleg. Der Pflichtpfad benötigt weder
kostenpflichtigen Schlüssel noch Modell-Download. Er ist von den Laboren 25–42
unabhängig. Die n8n-Instanz wird nur auf `127.0.0.1:15743` veröffentlicht;
der interne Python-Dienst und MCP-Prozess haben keinen Host-Port.

```sh
make ch43-verify
make ch43-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf
räumt sein Compose-Projekt selbst ab; `make ch43-down` (im Kapitelordner
`make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort
von Hand gestartet haben.

`make ch43-live` startet und entfernt nur sein eigenes temporäres Compose-Projekt
einschließlich seines Test-Volumes. Ergebnis: `reports/live-observation.json`.
Ein erfolgreicher Lauf zeigt acht Fälle, darunter Rollen-/Mandantenverweigerung,
OCR-Quarantäne und Ablehnung ohne Evidenz. Der Fall `old_wording_current_version`
nennt die alte Frist „fünf Tage“ und endet mit `answered` aus Version 2; Version 1
darf nicht einmal Kandidat sein. Ein bewusst generierter Testschlüssel läuft nach
fünf Minuten ab und wird nicht gespeichert.

Unauthorized Retrieval: Nach den acht Webhook-Fragen ruft das Skript das MCP-Tool
im laufenden `knowledge`-Container mit denselben Fragen und Tokens direkt auf
(`docker compose exec`). So sieht es die Kandidatenlisten vor dem Antwort-Gate,
die der Webhook nicht ausgibt; ihre Länge muss zu `retrieved_count` passen.
`core.unauthorized_retrieval` zählt die Anfragen mit mindestens einem Kandidaten,
der nicht zu einem aktuellen, freigegebenen und für Mandant und Gruppen des Tokens
lesbaren Abschnitt passt (Quell-ID, Version, Abschnitt, Digest), geteilt durch
**alle** Anfragen, positive wie negative. Der Bericht enthält die Kennzahl unter
`unauthorized_retrieval` und die Kandidaten-IDs je Fall unter `candidates`. Jeder
Wert über null lässt den Lauf scheitern. `make ch43-verify` prüft dieselbe
Kennzahl offline, auch mit zwei absichtlich undichten Varianten: Rechtefilter
abgeschaltet (2 von 8) und veraltete Version 1 als zusätzlicher Kandidat bei der
positiven Reisefrage (1 von 8, Antwort trotzdem korrekt).

Optional mit bereits installiertem Ollama-Modell:

```sh
CH43_OLLAMA_MODEL=qwen3:14b make ch43-ollama
```

Im Kapitelordner gleichwertig: `CH43_OLLAMA_MODEL=qwen3:14b make ollama`.

Dieser Versuch schreibt einen datierten Modell-/Digest-Bericht. Das Gate lehnt
jede Paraphrase oder falsch kopierte Fundstelle ab; ein `gate_accepted=false`
ist ein sicherer, aber inhaltlich schwächerer Modelllauf. Es gibt keinen
automatischen Download. OpenAI/Anthropic sind hier Architekturvarianten, keine
im Labor getesteten Ausgabepfade.

Grenzen: HMAC-Testidentität ist kein OIDC; die Zeichenähnlichkeit ist kein
Embedding; JSON-Dateien sind keine transaktionale DB; die OCR-Qualität ist ein
synthetischer Messwert, nicht ein tatsächlicher Tesseract-Lauf. Für Produktion
braucht es Identitätsprovider, geschützte Secret-Verwaltung, PostgreSQL-RLS,
transaktionale Versionierung, echten Parser/OCR, geprüftes Modell, Egress- und
Auditkonzept. Insbesondere ist ein veröffentlichter n8n-Webhook ohne vorgeschaltete
Authentisierung nicht als produktive Zugriffsschicht geeignet.
