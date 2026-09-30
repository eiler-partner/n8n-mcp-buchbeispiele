# Begleitprojekt: Fortgeschrittene MCP-Servermuster

Ein MCP-Server mit Job-Lebenszyklus fuer eine synthetische Dokumentenpruefung:
Progress (`review_now`), langlebige Jobs (`start_review`, `get_review`,
`cancel_review`) und Contract Tests ohne Netzwerk.

## Lokal

```bash
uv sync
uv run pytest
uv run mcp dev src/advanced_policy_mcp/server.py:mcp
```

Soll-Ergebnis: vier Tests bestehen. Im Inspector meldet `review_now`
Fortschritt; ein Job durchlaeuft `queued`, `running` und `succeeded` oder wird
waehrend `running` zu `cancelled`. Eine unbekannte `review_id` ergibt einen
`ToolError`, keinen Stacktrace.

## Container

```bash
docker build -t buch-ch18 .
docker run --rm -p 127.0.0.1:8000:8000 buch-ch18
```

Der Container startet den Server ueber Streamable HTTP unter
`http://127.0.0.1:8000/mcp`. Beenden mit `Strg+C`.
