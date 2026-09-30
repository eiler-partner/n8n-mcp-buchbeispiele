# Kapitel 44: eigenständige Recherche- und Datenanalyse-Pipeline

Synthetische API, HTML-Seite und CSV-Datei werden über n8n und ein read-only
MCP-Tool zu einem quellengebundenen Briefing verarbeitet. Die Pflichtabnahme
braucht weder Internet noch kostenpflichtige API noch Modell-Download. Sie
setzt keine Dienste aus Kapitel 43 voraus.

```sh
make ch44-verify
make ch44-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf
räumt sein Compose-Projekt selbst ab; `make ch44-down` (im Kapitelordner
`make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort
von Hand gestartet haben.

Der erste Lauf prüft die Pipeline ohne Docker. Der zweite startet einen nur
für dieses Kapitel angelegten Compose-Stack, führt den echten n8n-Webhook aus
und entfernt anschließend nur sein temporäres Testprojekt und Volume. Das
Ergebnis steht in `reports/live-observation.json`. Erwartet: drei angenommene,
vier gesperrte Quellen; zwei deduplizierte Werte; ein offener Konflikt bei
Bestellungen (`1200` in API/HTML gegen `1198` in CSV). Jede Aussage enthält
Quelle, Rohdigest, Fundstelle, Abruf-/Publikationszeit und Verarbeitungsschritte.

TDM-Vorprüfung: Der Quellendienst fragt jede HTTP-Quelle zuerst mit `HEAD` an.
Die Antwort hat keinen Body. Bei `tdm-reservation: 1` (`tdm_reserved`) oder
einem unbekannten Wert (`tdm_unknown`) folgt kein `GET`; der Body wird weder
übertragen noch gezählt noch gespeichert. Nur ohne Vorbehalt folgt `GET`, dessen
Header erneut geprüft werden. Auch der Redirect fällt schon beim `HEAD` auf. Der
Fixture-Server beantwortet `HEAD` mit denselben Headern wie `GET`, ohne Body.
Sein Audit (`fixture_http_requests` im Bericht) hält `<Methode> <Pfad>` fest; der
Live-Test verlangt `HEAD /web/tdm` und verbietet `GET /web/tdm`. Eine Quelle,
die `HEAD` mit einem Fehler beantwortet, stoppt den Auftrag; einen GET-Ersatzweg
gibt es bewusst nicht.

Optional für einen bereits installierten Ollama-Tag:

```sh
CH44_OLLAMA_MODEL=qwen3:14b make ch44-ollama
```

Im Kapitelordner gleichwertig: `CH44_OLLAMA_MODEL=qwen3:14b make ollama`.

Der Modelltext ist eine datierte, **nicht veröffentlichte** Interpretation.
Die Pflichtaussagen bleiben deterministisch. Kein automatischer Download.

Grenzen: Die HTTP-Quellen sind ein lokaler Fixture-Server, keine echte
Webrecherche. `robots.txt`, TDMRep und Nutzungsbedingungen werden als getrennte
Prüfsignale behandelt, nicht als vollständige juristische Freigabe. Die
Quellenliste ist fest, Redirects werden nicht verfolgt. Für Produktion wären
Domain-/IP-Egressschutz, belastbare Lizenzprüfung, Rate Limits, Versionierung,
Retry/Backoff, identitätsgebundene Quellenzugriffe und Datenschutzreview nötig.
