# Kapitel 35: Kontext und Belege

Eigenständiges, vollständig synthetisches Lehrlabor. Python 3.11+ genügt für
den Pflichtvertrag; Docker Desktop ist nur für den n8n-/MCP-Livepfad nötig.
Weder API-Schlüssel noch Modell-Download werden benötigt.

```sh
make ch35-verify
make ch35-live
make ch35-down
```

Die Befehle im Repository-Root starten nur den Compose-Projektnamen
`buch-ch35`. Im Kapitelordner `code/ch35` gelten gleichwertig `make test`,
`make live` und `make down`. `make ch35-down` entfernt Container und Netzwerk, **nicht** das
benannte n8n-Postgres-Volume. Port 15735 ist n8n, 8135 der Lehrdienst.

```sh
curl -sS -X POST http://127.0.0.1:15735/webhook/ch35-citations \
  -H 'Content-Type: application/json' \
  --data '{"action":"answer","case_id":"urlaub"}' | python3 -m json.tool
```

Weitere Fälle: `konflikt` (widersprechende aktuelle Quellen),
`hr-verweigert` (keine autorisierte Evidenz), `hr-erlaubt` (nur Fixture-
Rollenfall). Die Rolle ist im Fallkatalog fixiert, nicht durch einen
HTTP-Parameter beweisbar. Der n8n-Webhook ist **nicht authentifiziert**;
niemals außerhalb von Loopback veröffentlichen. Für einen echten Einsatz
braucht es Identität, Autorisierung und dokumentierte Datenflüsse an jedem
Eintrittspunkt.

Mit `action=verify` und `claims=[...]` lässt sich eine Satzliste gegen den
gepackten Kontext prüfen. Ein Beleg enthält Chunk-/Dokument-ID, Version,
Seite, Absatz, SHA-256 und wörtlichen Auszug. Der Validator prüft die
Provenienz und vergleicht die Aussage zusätzlich mit dem geschlossenen,
synthetischen Fallvertrag. Das ist **kein allgemeiner semantischer
Wahrheitsbeweis**. Für freie Modellantworten wäre zusätzlich ein evaluiertes
Entailment-Verfahren oder menschliche Prüfung erforderlich.

Der MCP-Adapter `mcp_stdio.py` ist ein enges `resources/list`-/`resources/read`-
Subset für den festen Mitarbeiterscope. Es implementiert keinen vollständigen
Server-Lifecycle und ist keine Produktionsvorlage. Der Live-Prüflauf testet,
dass HR-Ressourcen dort nicht aufgelistet oder gelesen werden.
