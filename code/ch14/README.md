# Kapitel 14: Wire-Labor für zwei MCP-Revisionen

Der offizielle Python-MCP-Server (`mcp==2.2.0`) bedient eine ausschließlich
synthetische, lesende Operation. `capture.py` ist absichtlich ein kleiner
Rohclient: Er schreibt die JSON-RPC-Nachrichten selbst über `stdio` und
speichert genau die empfangenen Antworten. Die Dateien unter `traces/`
sind solche echten lokalen Aufzeichnungen, keine erfundenen SDK-Ausgaben.
Es gibt weder Cloud-Konto noch Schlüssel noch echte Dokumente.

## Start und eigener Mitschnitt

```sh
cd code/ch14
uv sync --frozen --dev
uv run python -m mcp_wire_lab.capture legacy --output traces/legacy.json
uv run python -m mcp_wire_lab.capture modern --output traces/modern.json
uv run python -m mcp_wire_lab.validate traces/legacy.json
uv run python -m mcp_wire_lab.validate traces/modern.json
uv run pytest
```

Die Revisionsauswahl wird **vom Rohclient** getroffen. Bei `legacy` sendet er
`initialize`, wartet auf dessen Antwort und sendet
`notifications/initialized`. Bei `modern` sendet er einen optionalen
`server/discover`-Aufruf. In beiden Fällen folgt `tools/call` für
`read_policy` und `DOC-101`. Dass der SDK-Server beide Formen annimmt,
wurde mit den aufgezeichneten Frames überprüft.

Ohne lokale Python-Installation lässt sich der Prüflauf im Container
ausführen:

```sh
docker compose run --build --rm wire-lab
```

Die Container-Netzwerkverbindung ist zur **Laufzeit** ausgeschaltet. Für den
erstmaligen Image-Bau müssen Docker und `pip` die gepinnten Pakete laden
können. Alle Tests und Mitschnitte danach arbeiten ohne Netzwerk.

## Fehlerlabor

Die Tests verändern Kopien der positiven Traces und erwarten jeweils eine
präzise Diagnose: JSON-Parse-Fehler, falsches `jsonrpc`, unpassende
Antwort-ID, Notification mit ID, Batch-Array, fehlende moderne `_meta`-
Pflichtfelder, fehlendes `resultType`, falsche Protokollversion,
Header/Body-Mismatch und zu früher Legacy-Toolaufruf.

Für eine eigene Reparatur kopieren Sie `traces/modern.json` unter einen
anderen Namen, ändern Sie z. B. bei `tools/call` den Wert von
`io.modelcontextprotocol/protocolVersion` und prüfen Sie die Kopie mit
`mcp_wire_lab.validate`. Stellen Sie genau diesen Wert wieder her und
prüfen Sie erneut. Eine zweite Übung ändert nur die Antwort-ID. Die
Originaltraces bleiben unverändert; der Validator zeigt jeweils Schicht,
Frame und Fehlercode.

Der Validator kombiniert das generische Nachrichtenmodell aus dem
versionsgepinnten offiziellen Python-SDK mit expliziten Regeln für
Reihenfolge, Version, ID-Korrelation und HTTP-Header. Das SDK-Modell
ersetzt nicht die zustandsabhängigen Regeln. Die beiden normativen
Revisionsschemata sind
[`2025-11-25`](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-11-25/schema.ts)
und
[`2026-07-28`](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2026-07-28/schema.ts);
die Texte der Spezifikation bestimmen die zusätzlichen Sequenzregeln.
Die HTTP-Header werden als **separater, synthetischer Prüffall** getestet,
weil die positiven Mitschnitte über `stdio` und damit ohne HTTP laufen.

`uv.lock` fixiert die aufgelösten Paketversionen. Docker verwendet dieselbe
Lockdatei; die SDK-Version `mcp==2.2.0` ist zudem im Projektvertrag festgelegt.
