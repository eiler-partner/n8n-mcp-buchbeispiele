# Begleitprojekt Kapitel 17: der erste MCP-Server mit dem Python-SDK v2

Ein kleiner MCP-Server („Policy Lab“) mit zwei Tools (`hash_text`,
`search_policies`), einer Resource (`policy://{policy_id}`) und einem Prompt
(`review_policy`). Das Kapitel baut ihn Schritt für Schritt auf; dieser Ordner
enthält den fertigen Stand.

Voraussetzungen: Python 3.12 oder neuer und `uv`. Für den Inspector zusätzlich
Node.js mit `npx`.

## Prüfen ohne Netzwerkdienst

```bash
cd code/ch17
uv sync --locked --dev
uv run pytest
```

Soll-Ergebnis: drei Tests bestehen (Domänenfunktion, MCP-Vertrag von
`hash_text` und das Lesen der Resource `policy://POL-101`). Aus dem Wurzelordner des Buchs geht dasselbe mit
`make ch17-verify`.

## Im Inspector ausprobieren

```bash
uv run mcp dev src/policy_mcp/server.py
```

Der Befehl startet den Server über stdio und öffnet den MCP Inspector. Unter
„Tools“ erscheinen `hash_text` und `search_policies`. Ein Aufruf von
`hash_text` mit demselben Text liefert immer denselben SHA-256-Wert.
Beenden mit `Strg+C`.

## Als Container

```bash
docker build -t buch-ch17 .
docker run --rm -i buch-ch17
```

Der Container startet den Server über stdio (`uv run policy-mcp`). Er wartet
dann auf JSON-RPC-Nachrichten auf der Standardeingabe; ohne Client passiert
sichtbar nichts. Beenden mit `Strg+C`. Ein HTTP-Beispiel mit Port folgt in
`code/ch18`.
