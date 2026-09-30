# Kapitel 33 – Embeddings und Vektorspeicher

Eigenständiges, ausschließlich synthetisches Labor für PostgreSQL/pgvector,
Qdrant, n8n und einen kleinen MCP-Tool-Adapter. Die Vektoren sind handgesetzte
Testkoordinaten und **keine** Ausgaben eines Embedding-Modells. Die verdichtete
Richtlinie lehnt sich an Kapitel 32 an, benötigt dessen Stack aber nicht.

## Start und Prüfung

Aus dem Wurzelverzeichnis des Begleitmaterials:

```sh
make ch33-verify
make ch33-live
make ch33-down
```

Im Kapitelordner `code/ch33` gelten gleichwertig `make test`, `make live`,
`make ollama` und `make down`.

Der schnelle Vertragstest benötigt nur Python. Der Live-Lauf startet den
eigenen Docker-Compose-Stack, lädt beide Vektorräume idempotent, prüft n8n,
beide Speicher, Rollen-/Versionsfilter, die Gleichstandsregel und MCP und
schreibt `reports/live-observation.json`. Image-Downloads sind beim ersten
Start möglich; es wird kein Modell geladen und kein bezahlter Schlüssel
verwendet.

Beide Speicher ordnen nach derselben Regel: Score absteigend, bei gleichem
Score `chunk_id` aufsteigend in Bytereihenfolge. In SQL steht dafür
`ORDER BY distance, chunk_id COLLATE "C"`. Qdrant hat keine solche Regel. Der
Adapter fragt dort deshalb `top_k + 4` Punkte an und vergrößert das Limit,
solange der letzte gelieferte Score noch dem Score auf Platz `top_k` gleicht.
Dann sortiert er nach derselben Regel und schneidet auf `top_k` ab. Der
Live-Lauf prüft das mit dem Anfragevektor `[1.0, 1.0, 0.1, 0.1]`: Urlaub und
Reisekosten haben dazu denselben Score, und beide Speicher müssen
`v2-travel` vor `v2-vacation` liefern.

Optional, falls `all-minilm:latest` bereits lokal in Ollama installiert ist:

```sh
make ch33-ollama
```

Dieser reine Modell-Formtest fragt neun synthetische Texte ab und schreibt
`reports/ollama-observation.json` mit Modell-Digest und Datum. Er lädt selbst
kein Modell nach und behauptet keine allgemeine Retrieval-Qualität.

Die Dienste binden ausschließlich an `127.0.0.1`:

- n8n-Webhook `http://127.0.0.1:15733/webhook/ch33-vectors`
- Python-Vertragsdienst `http://127.0.0.1:8133/operate`
- Qdrant `http://127.0.0.1:16333`
- PostgreSQL `127.0.0.1:15433`

Die Passwörter im Compose-File sind nur lokale Laborwerte. Der Webhook ist
**nicht authentifiziert**; Rollenangaben werden nur für Filtertests verwendet.
Der MCP-Adapter ist ein Lehr-Subset und keine produktive Bereitstellung.

## Wiederholung und Aufräumen

`make ch33-live` ist wiederholbar. Zum Stoppen nur dieses Kapitelstacks:

```sh
make ch33-down
```

Benannte Volumes bleiben dabei erhalten. Wer sie löschen will, muss die
**drei konkreten Kapitel-33-Volumes** zuvor prüfen und separat freigeben;
`make ch33-down` löscht sie absichtlich nicht.
