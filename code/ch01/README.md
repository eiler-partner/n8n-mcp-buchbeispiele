# Kapitel 1: E-Mail-Klassifikation vergleichen

Das Labor ist eigenständig, benötigt nur Python 3.12 und verwendet erfundene
E-Mails. Der Standardlauf spielt vorab festgelegte Modellantworten ab. Diese
Fixture demonstriert Fehlertypen und ist **kein** Leistungsnachweis eines
aktuellen Modells.

```bash
python3 email_lab.py --provider rules
python3 email_lab.py --provider fixture
python3 -m unittest discover -s tests -v
```

Die Ausgabe enthält Soll- und Ist-Kategorie je E-Mail, wörtliche Textbelege,
Fehlzuordnungen, Enthaltungen und Vertragsfehler. `e11` ist in der Modell-Fixture
absichtlich falsch. `e04` und `e07` zeigen Grenzen der starren Regelpriorität.
Eine `unsicher`-Zuordnung ist eine Übergabe zur menschlichen Prüfung; eine
unlesbare Providerantwort wird separat als `vertrag_fehler` gezählt.

Mit Docker lässt sich derselbe Test ohne lokale Python-Installation ausführen:

```bash
docker build -t buch-ch01 .
docker run --rm buch-ch01
docker run --rm --entrypoint python buch-ch01 email_lab.py --provider fixture
```

Optionale Live-Runden verwenden dasselbe Schema. Modell-IDs sind bewusst nicht
fest codiert, weil Verfügbarkeit und Versionen wechseln. Die erfundenen Texte
werden an den gewählten Provider gesendet; mögliche Kosten und Datenrichtlinien
sind vor dem Aufruf zu prüfen. In produktiven Umgebungen sind Image-Digests und
Modell-Snapshots festzulegen.

```bash
OPENAI_API_KEY=... python3 email_lab.py --provider openai --model MODELL_ID
ANTHROPIC_API_KEY=... python3 email_lab.py --provider anthropic --model MODELL_ID
python3 email_lab.py --provider ollama --model LOKALES_MODELL
```

Für Ollama kann `CH01_OLLAMA_URL` die API-Adresse setzen. Bei einem
Containerlauf auf macOS und nativem Ollama ist beispielsweise
`http://host.docker.internal:11434` möglich. Live-Runden sind optional und
werden nicht zur Kapitelabnahme benötigt. Der Parser prüft die Struktur und
einen wörtlichen Beleg, kann aber die fachliche Richtigkeit der Klassifikation
nicht beweisen.
