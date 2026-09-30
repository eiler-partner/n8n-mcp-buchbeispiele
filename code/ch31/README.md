# Kapitel 31 – Dokument-Ingestion und OCR

Eigenständiges Labor mit ausschließlich synthetischen PDF-Dateien. Docker Desktop/Compose und Python 3.12 genügen; keine API-Schlüssel, keine LLM- oder Embedding-Downloads. Der Docker-Build erzeugt die drei Fixtures aus `scripts/build_fixtures.py` und dem versionierten Text in `data/cases.json`.

Vom Repository-Wurzelverzeichnis:

```sh
make ch31-verify
make ch31-live
make ch31-down
```

Im Kapitelordner `code/ch31` gelten gleichwertig `make test`, `make live` und `make down`. Der Live-Lauf startet nur den Stack `buch-ch31`, prüft den publizierten n8n-Webhook, den Python-Ingestionsdienst und das MCP-Resource-Lehrsubset und schreibt `code/ch31/reports/live-observation.json`. Manuell:

```sh
curl -sS -X POST http://127.0.0.1:15731/webhook/ch31-ingest \
  -H 'Content-Type: application/json' \
  --data '{"case_id":"digital","declared_mime":"application/pdf"}'
```

Setzen Sie `case_id` nacheinander auf `digital`, `scan_good` und `scan_cropped`. Die ersten beiden müssen `accepted`, der beschnittene Scan `quarantined` mit `missing_required_phrase` liefern. Bei wiederholter Einlieferung desselben PDF-Bytesatzes wird `duplicate: true` zurückgegeben; der ursprüngliche Status bleibt erhalten. Ein unpassender deklarierter MIME-Typ oder ein zwischen Vorprüfung und Commit anderer SHA-256-Quellhash wird abgewiesen.

Das digitale PDF wird über seine Textebene verarbeitet. Die Bild-PDFs werden auf 300 dpi gerastert und mit Tesseract `deu` erkannt. Die Wortkonfidenz aus TSV ist **kein** Wahrheits- oder Vollständigkeitsbeweis. Das Labor kann zusätzlich gegen seinen bekannten Referenztext eine Zeichenfehlerrate rechnen; in echten Eingangsdaten fehlt dieser Goldtext normalerweise. Dort wären Stichproben, strukturelle Pflichtfelder, Validierungsregeln und Review nötig. Die Schwellen 70 für mittlere OCR-Wortkonfidenz und 0,12 für Zeichenfehlerrate sind ausschließlich Lehrwerte.

Der n8n-Workflow führt Vorprüfung/Extraktion und Commit/Quarantäne getrennt aus. Der Commit verarbeitet die bekannte Fixture erneut und prüft den zuvor beobachteten Quellhash, damit ein zwischenzeitlich geänderter Eingang nicht still auf einen alten Vorprüfbericht gestützt wird. Ein späterer Index darf nur `accepted` übernehmen. Über den MCP-stdio-Adapter sind entsprechend nur freigegebene Texte lesbar. Der Adapter ist ein **Resource-Lehrsubset**, kein vollständiger Produktionsserver; er besitzt keine Nutzeranmeldung.

Office-Dateien, HTML, E-Mails und freie Uploads werden im Kapitel architektonisch behandelt, aber absichtlich nicht als angeblich geprüfte Parserpfade ausgegeben. Der Pflichtlauf verarbeitet nur die drei bekannten PDFs. Ebenso sind die Quarantäne und die SQLite-Datenbank lokale Demonstratoren, keine Malware-Analyse oder rechtssichere Archivierung.

Zum Aufräumen:

```sh
make ch31-down
```

Das entfernt nur die Kapitel-31-Container und ihr Netzwerk; die beiden Kapitel-Volumes bleiben für einen späteren Wiederanlauf erhalten.
