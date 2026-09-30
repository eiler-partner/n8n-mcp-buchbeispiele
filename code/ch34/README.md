# Kapitel 34 – semantische, lexikalische und hybride Suche

Unabhängiges, ausschließlich synthetisches Lehrlabor. Die obligatorischen
vierdimensionalen Vektoren sind handgesetzte Prüfdaten, keine Modell-
Embeddings. PostgreSQL 17 führt echte deutsche Volltextsuche und exakte
pgvector-Cosine-Suche aus. Python fusioniert die vorgefilterten Listen mit
offengelegtem RRF-Parameter. n8n leitet den lokalen Webhook weiter; der
MCP-Adapter demonstriert einen gesonderten serverseitigen Mitarbeiterscope.

Aus dem Wurzelverzeichnis des Begleitmaterials:

```sh
make ch34-verify
make ch34-live
make ch34-down
```

Im Kapitelordner `code/ch34` gelten gleichwertig `make test`, `make live`,
`make ollama` und `make down`.

`ch34-verify` benötigt nur Python. `ch34-live` startet ausschließlich den
Stack `buch-ch34`, lädt den Korpus wiederholbar und schreibt
`code/ch34/reports/live-observation.json`. Beim ersten Docker-Start können
Images geladen werden; es wird kein LLM oder Embedding-Modell nachgeladen.
Der Stack bindet seine Laborports ausschließlich an `127.0.0.1`: n8n-WebHook
`15734`, Vertragsdienst `8134`, PostgreSQL `15434`.

Beispiel nach dem Start:

```sh
curl -sS -X POST http://127.0.0.1:15734/webhook/ch34-retrieval \
  -H 'Content-Type: application/json' \
  --data '{"action":"search","case_id":"vacation-frist","mode":"hybrid"}'
```

Gültige Modi: `lexical`, `lexical_expanded`, `dense`, `hybrid`,
`hybrid_expanded`. `lexical_expanded` führt nur den FTS-Zweig mit der
freigegebenen erweiterten Query aus, ohne Fusion. So sehen Sie, ob die
Expansion den FTS-Zweig selbst verändert:

```sh
for mode in lexical lexical_expanded hybrid hybrid_expanded; do
  curl -sS -X POST http://127.0.0.1:15734/webhook/ch34-retrieval \
    -H 'Content-Type: application/json' \
    --data "{\"action\":\"search\",\"case_id\":\"rkk-frist\",\"mode\":\"$mode\"}"
  echo
done
```

Für `rkk-frist` erwartet der Live-Prüfer: `lexical` findet nichts,
`lexical_expanded` findet genau `v2-travel`. Die fusionierten Top-IDs von
`hybrid` und `hybrid_expanded` bleiben gleich, weil der Vektorzweig
`v2-travel` schon auf Rang 1 hat; nur dessen RRF-Score steigt von 1/61 auf
2/61. Der Prüfer gibt diesen Vergleich aus und schreibt ihn als
`fts_expansion_rkk_frist` in den Bericht.

`evaluate` liefert die Metriken für alle sieben gelabelten Fälle in allen fünf
Modi (35 Suchläufe). Der Dienst ist **nicht authentifiziert**; Rollen stammen
in diesem Lehrlabor aus fest definierten Fällen und sind kein produktiver
Berechtigungsnachweis.

Für den freiwilligen echten Form- und Rangvergleich mit einem **bereits
installierten** Ollama-Modell:

```sh
make ch34-ollama
```

Dieser Prüfer lädt kein Modell nach und speichert Datum, Digest, Dimension und
beobachtete Treffer nach `reports/ollama-observation.json`. Der Modelllauf
ändert die Pflichtabnahme nicht. Zum Stoppen: `make ch34-down`.
Benannte Volumes bleiben erhalten; kein anderes Kapitel wird berührt.
