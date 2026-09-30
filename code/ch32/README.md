# Kapitel 32 – Chunking, Metadaten und Versionierung

Eigenständiges, ausschließlich synthetisches Labor. Es benötigt Docker Desktop/Compose und Python 3.12, aber weder API-Schlüssel noch Modell-Downloads. Der Python-Dienst hält einen lokalen SQLite-Chunk-Index; der publizierte n8n-Webhook orchestriert Publikation und Sichtabfrage. MCP ist ein begrenztes stdio-Resource-Lehrsubset. Kein Vektorspeicher und keine semantische Suche werden behauptet.

Vom Repository-Wurzelverzeichnis:

```sh
make ch32-verify
make ch32-live
make ch32-down
```

Im Kapitelordner `code/ch32` gelten gleichwertig `make test`, `make live` und `make down`. `ch32-verify` prüft die strukturtreuen Grenzen, die atomare Versionsumschaltung, einen erzwungenen Rollback, Rechte- und Stichtagfilter, logischen Rückzug und MCP-Read-Denial ohne Docker. `ch32-live` startet nur `buch-ch32`, prüft den **publizierten** n8n-Webhook sowie MCP-Resources und schreibt `code/ch32/reports/live-observation.json`. Der Lauf ist wiederholbar: erneute Publikation und Rückzug mit denselben Daten liefern `duplicate: true`, historische Abfragen bleiben datiert nachvollziehbar.

Manuell über n8n, zum Beispiel nach `make ch32-live`:

```sh
curl -sS -X POST http://127.0.0.1:15732/webhook/ch32-policy \
  -H 'Content-Type: application/json' \
  --data '{"action":"visible","as_of":"2026-09-29","role":"employee"}'
```

Die aktuelle Mitarbeitersicht enthält `15 Arbeitstage` und `30 Kalendertage`, aber weder die alte Zehntage-Regel noch die synthetische HR-Kennung. `as_of=2026-08-31` zeigt die historische Fassung; `as_of=2026-10-02` zeigt nach dem datierten Rückzug keine Chunks. Der historische Bestand bleibt im Lehrspeicher erhalten. **Das ist keine physische Löschung.** Rollen im HTTP-Request sind nicht authentifiziert; der Dienst ist nur an Loopback veröffentlicht. Die MCP-Spur erhält ihren Labor-Scope dagegen aus der serverseitigen Prozessumgebung und ignoriert Identitätsbehauptungen in `clientInfo`.

Die Vergleichsbasis teilt alle 170 Zeichen, auch mitten im Wort. Die freigegebene Variante hält Paragraphen, ganze Sätze und die Tabelle zusammen; sie verwendet `structure-v1` und speichert IDs, Hashes, Parent, Quelle, Version, Rolle und Gültigkeit. Das Größenlimit ist ein Zeichenlimit, **kein** modellabhängiges Tokenlimit. Semantische Segmentierung, Embeddings und Ranking folgen später.

Zum Aufräumen:

```sh
make ch32-down
```

Dies entfernt nur Kapitel-32-Container und Netzwerk; die zwei benannten Test-Volumes bleiben erhalten. Ein bewusster vollständiger Reset der ausschließlich synthetischen Kapitel-32-Daten wäre `docker compose down -v` im Verzeichnis `code/ch32`; er wird nie automatisch ausgeführt.
