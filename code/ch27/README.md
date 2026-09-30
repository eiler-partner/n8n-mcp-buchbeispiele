# Kapitel 27: Agenten, Zustände und Gedächtnis

Das eigenständige Labor zeigt **einen deterministischen Agentenentscheid als Fixture**, nicht die Leistungsfähigkeit eines Modells. Der Python-Dienst speichert Laufzustand, Gesprächsnachrichten und eine synthetische Toolwirkung in getrennten SQLite-Tabellen. n8n bietet zwei Webhooks für Start und Fortsetzung. Ein Restart und ein absichtlich verlorenes HTTP-Acknowledgement sind Teil der Gegenprobe.

## Voraussetzungen und Versionen

- Python 3.12 oder neuer für die schnellen Tests; nur Standardbibliothek.
- Docker Desktop/Compose für den Live-Pfad; lokal gebundene Ports `8127` und `15727`.
- Images im Compose: `python:3.12-slim`, `postgres:17-alpine`, `n8nio/n8n:2.40.7`. Kein Modell-Download, kein Cloud-Schlüssel.
- Dieses Labor benötigt keinen Container eines früheren Kapitels. Die Laborpasswörter sind **nur** für Loopback-Testumgebungen gedacht.

## Schnelltest ohne Docker

Alle Befehle laufen aus dem Wurzelverzeichnis des Begleitmaterials. Im Kapitelordner `code/ch27` gelten gleichwertig `make test`, `make live` und `make down`.

```sh
make ch27-verify
```

Dreizehn Tests prüfen Zustand, Neustart mit derselben SQLite-Datei, Replay, konkurrierende Schlüssel, alte Revision, Mandantentrennung, Stop, Schrittbudget und Session-Löschung. Drei davon prüfen den Schlüssel der Tabelle `effects`: Eindeutig ist das Paar aus `run_id` und `effect_key`. Zwei verschiedene Aktionen desselben Laufs erhalten je einen Eintrag; ein Retry derselben Aktion erzeugt keinen zweiten. Einer dieser drei Tests stellt eine Tabelle in der alten Form um (siehe unten).

## Echter Integrations- und Neustarttest

```sh
make ch27-live
```

Der Befehl startet den isolierten Stack, importiert und publiziert den n8n-Workflow und führt den Test aus. Er startet den Python-Dienst und n8n während eines wartenden Laufs neu. Erwartet werden sieben `PASS`-Zeilen; der datierte Bericht liegt unter `reports/live-observation.json`. Ein wiederholter Lauf nutzt neue IDs und darf dasselbe Volume weiterverwenden. Stammt das Volume aus einer früheren Laborfassung, in der `run_id` allein der Primärschlüssel von `effects` war, stellt der Dienst die Tabelle beim Start einmalig auf den Schlüssel (`run_id`, `effect_key`) um. Vorhandene Einträge bleiben erhalten.

Manuell kann ein Lauf so begonnen werden:

```sh
curl -sS -X POST http://127.0.0.1:15727/webhook/ch27-start \
  -H 'Content-Type: application/json' \
  --data '{"run_id":"demo-27","tenant_id":"demo","session_id":"demo-session","text":"Synthetischer Wunsch","proposed_note":"Nur Labordaten","max_steps":2}'
```

Danach liefert `GET http://127.0.0.1:8127/runs/demo-27?tenant_id=demo` den Status `awaiting_resume`, Revision 1 und `effect_count=0`. Fortsetzung:

```sh
curl -sS -X POST http://127.0.0.1:15727/webhook/ch27-resume \
  -H 'Content-Type: application/json' \
  --data '{"run_id":"demo-27","tenant_id":"demo","resume_key":"demo-resume","expected_revision":1,"decision":"continue"}'
```

Die Antwort meldet `completed` und `effect_count=1`. Derselbe Auftrag mit demselben Schlüssel ist ein Replay ohne zweiten Effekt; ein anderer Schlüssel scheitert. `decision=stop` beendet ohne Effekt. `max_steps=1` beendet bereits nach der Fixture-Entscheidung mit `budget_exhausted`.

Die Session-Löschung ist ein bewusster **synthetischer Laborpfad**:

```sh
curl -sS -X POST http://127.0.0.1:8127/forget \
  -H 'Content-Type: application/json' \
  --data '{"tenant_id":"demo","session_id":"demo-session"}'
```

Sie löscht zugehörige Läufe, Nachrichten und lokale Toolwirkungen. Ein inhaltsarmer Tombstone sperrt die alten `run_id`s. Das ist keine allgemeine Datenschutz- oder Backup-Löschgarantie für andere Dienste.

## Grenzen und Aufräumen

Der Webhook und die Python-API besitzen **keine Authentifizierung**; die Ports sind nur an `127.0.0.1` gebunden. `tenant_id` ist ein Testparameter und keine geprüfte Identität. Für Produktion braucht es echte Authentifizierung, Autorisierung, TLS, Backups, Aufbewahrungsregeln und eine externe Idempotenzvereinbarung. Genau-einmal ist hier nur für die synthetische Wirkung innerhalb **derselben SQLite-Transaktion** nachgewiesen. Ein externer E-Mail-, MCP- oder Zahlungsdienst benötigt einen eigenen stabilen Idempotenzschlüssel und Gegenprüfungen.

```sh
make ch27-down
```

Das stoppt und entfernt nur die Kapitel-27-Container und das Netzwerk; die **eigenen Volumes bleiben erhalten**. Wer diese Labordaten später entfernen möchte, muss die konkreten Kapitel-27-Volumes gesondert prüfen und ausdrücklich löschen. Niemals globale Docker-Volumes pauschal bereinigen.
