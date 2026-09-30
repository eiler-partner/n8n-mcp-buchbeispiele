# Kapitel 13 – API auf MCP-Eignung prüfen

Dieses Labor ist eigenständig. Es nutzt nur erfundene Dokumente, eine kleine
Python-HTTP-API und drei Architektur-Entscheidungskarten. Es enthält **keinen
MCP-Server**: Erst wird begründet, ob und wo ein solcher Adapter sinnvoll wäre.
Es werden weder ein n8n- noch ein Modellkonto oder echte Credentials benötigt.

Die API besitzt absichtlich keine Authentifizierung. Sie ist nur für den
lokalen Versuch gedacht; insbesondere ist `POST /approvals` **keine echte
Freigabe**. Es legt lediglich einen flüchtigen Eintrag im Containerprozess an.
Beim Neustart verschwindet der Eintrag. Den Container nicht im Netzwerk
veröffentlichen; Docker bindet den Host-Port nur an `127.0.0.1`.

## Test und Start

Vom Buchprojektverzeichnis aus:

```sh
python3 -m unittest discover -s code/ch13/tests -v
python3 code/ch13/validate_decisions.py
cd code/ch13
docker compose up -d --build --wait
python3 verify_live.py
```

Die drei direkten API-Operationen von Hand prüfen:

```sh
curl -sS http://127.0.0.1:18072/documents/DOC-101 | python3 -m json.tool
curl -sS 'http://127.0.0.1:18072/search?q=Freigabe' | python3 -m json.tool
curl -sS -X POST http://127.0.0.1:18072/approvals \
  -H 'Content-Type: application/json' \
  --data '{"document_id":"DOC-101","decision":"approve"}' | python3 -m json.tool
```

`decisions.json` ist die Musterlösung, **keine** technische Freigabe. Die
Karten benennen je Operation Aufrufer, Datenklasse, Modellgrenze, Seiteneffekt,
Zuständigkeit und begründete Entscheidung. Mit
`python3 validate_decisions.py meine-karten.json` lassen sich eigene Karten
auf Vollständigkeit und einige Widersprüche prüfen. Der Validator kann
fachliche Zulässigkeit nicht entscheiden.

Erwartung: fester Abruf bleibt eine direkte API; die begrenzte Suche kann bei
mehreren unabhängigen Hosts ein MCP-Kandidat sein; die schreibende Aktion
bleibt ohne echte Identität, Objektberechtigung und Zustimmungsnachweis dem
Modell vorenthalten. Das sind **Szenarioentscheidungen**, keine allgemeingültige
Zuordnung aller Abrufe, Suchen und Schreibvorgänge.

## Abschluss

```sh
docker compose stop
```

Es gibt keine persistierten Daten. Ein erneuter Start setzt den simulierten
Freigabestatus zurück. Die Kapitel-10- und Kapitel-11-Labore werden nicht
verändert.
