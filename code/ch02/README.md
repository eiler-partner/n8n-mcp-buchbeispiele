# Kapitel 2: Architektur-Check

Das eigenstaendige Labor beschreibt einen fiktiven Dokumentenpruefungsprozess.
Es benoetigt weder API-Schluessel noch einen laufenden n8n- oder MCP-Dienst.

```sh
python3 code/ch02/validate.py code/ch02/architecture.json
python3 -m unittest discover -s code/ch02/tests -v
docker build -t buch-ch02 code/ch02
docker run --rm buch-ch02
```

Die Regeln in `validate.py` sind **Beispielrichtlinien** dieses Szenarios und
kein allgemeiner Standard. Aendern Sie in einer Kopie der JSON-Datei etwa die
Klassifikation des Modellaufrufs zu `confidential` oder entfernen Sie die
Freigabe an der Schreib-API. Der Check muss dann fehlschlagen. Eine bestandene
Pruefung ersetzt keine Inhalts-, Rechte- und Sicherheitspruefung des realen
Systems. Die Komponenten muessen insbesondere noch mit konkreten API-Schemata,
Identitaeten, Aufbewahrungsfristen und Fehlerwegen hinterlegt werden.
