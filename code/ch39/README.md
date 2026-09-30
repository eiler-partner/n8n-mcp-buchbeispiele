# Kapitel 39: Queue Mode und begrenzter Lasttest

Eigenständiger, nur lokal erreichbarer n8n-Stack mit PostgreSQL, Redis,
separatem Main, Webhook-Prozessor und einem Worker mit eigenem externen
Python-Runner. Das optionale Profil `scale` fügt ein zweites Worker-Runner-Paar
hinzu. Der synthetische Python-Dienst simuliert eine kurze I/O-Wartezeit; es
werden keine echten Nutzerdaten, Modelle oder API-Schlüssel verwendet.

Voraussetzungen: Docker Desktop/Engine, Compose und Python 3.9+ auf dem Host.
Vom Projektverzeichnis aus:

```bash
make ch39-verify
make ch39-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf
räumt sein Compose-Projekt selbst ab; `make ch39-down` (im Kapitelordner
`make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort
von Hand gestartet haben. Einen Ollama-Lauf hat Kapitel 39 nicht.

Der Live-Test erzeugt temporäre Secrets und einen eindeutigen Compose-
Projektnamen. Er misst nacheinander 18 Requests mit einem Worker, 18 Requests
mit zwei Workern und acht Requests nach dem Stoppen von Worker 1. Für jeden
Lauf stehen Fehlerzahl, p50/p95-Latenz, Durchsatz und maximale gleichzeitig
aktive Fixture-Aufrufe im datierten Bericht `reports/live-observation.json`.
Das ist ein begrenzter Funktionstest, **kein** Leistungsversprechen.

Nur `127.0.0.1:15739` (Webhook-Prozessor) und `127.0.0.1:15740` (Main/Editor)
werden am Host veröffentlicht. Die Testinstallation verwendet HTTP nur auf
Loopback; TLS und externe Authentisierung sind Gegenstand von Kapitel 38 und
vor einem öffentlichen Betrieb zusätzlich zu prüfen. Redis ist in diesem
wegwerfbaren lokalen Test absichtlich ohne Passwort und ohne Persistenz;
das ist keine Produktionskonfiguration. Alle temporären Container, Netze,
Volumes und Secret-Dateien dieses Testlaufs werden anschließend entfernt.

Die Queue-Datenbank enthält nur synthetische IDs. Ein grüner Worker-Test
garantiert keine Main-Hochverfügbarkeit; Multi-Main ist editionsabhängig.
