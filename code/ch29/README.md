# Kapitel 29: Zwei Freigaben vor einer schreibenden Aktion

Das eigenständige Labor hält einen **synthetischen** Schreibvorschlag in einer lokalen SQLite-Datenbank. Zwei getrennte n8n-Formulare erfassen Entscheidungen; erst der Python-Dienst gibt nach Eigentümer- und Zweitfreigabe eine einzige lokale Outbox-Schreibaktion frei. Eine Ablehnung oder ein Ablauf schreibt nichts. Der Eskalationsweg ersetzt nur die zweite Freigabe und benötigt eine andere Akteur-ID als die erste.

Die Akteur-IDs in den Formularen sind **nicht authentifiziert**. Das Labor demonstriert einen Zustands- und Toolvertrag, kein produktionsreifes Vier-Augen-System. Es gibt weder eine echte E-Mail noch einen Cloud-API-Aufruf oder ein Modell.

## Voraussetzungen und Abnahme

- Python 3.12 oder neuer für Tests und Prüfsystem; Laufzeit nur Standardbibliothek.
- Docker Desktop/Compose für den n8n-Pfad; Images `python:3.12-slim`, `postgres:17-alpine` und `n8nio/n8n:2.40.7`.
- Ports ausschließlich auf `127.0.0.1`: Gate `8129`, n8n `15729`.

Aus dem Wurzelverzeichnis des Begleitmaterials:

```sh
make ch29-verify
make ch29-live
```

Im Kapitelordner `code/ch29` gelten gleichwertig `make test`, `make live` und `make down`. `make ch29-verify` prüft die Zustandsmaschine ohne Docker. `make ch29-live` baut den isolierten Stack, startet drei unabhängige synthetische Fälle und schreibt `reports/live-observation.json`. Die Live-Prüfung nutzt beide n8n-Formulare, einen Ablehnungspfad und den n8n-Eskalationswebhook. Sie testet zusätzlich Schreibsperre vor Freigabe, gleiche Akteur-ID, veränderten Entwurf und doppelten Schreibaufruf.

## Von Hand nachvollziehen

Bei laufendem Stack, etwa nach `make ch29-live`, einen neuen, nur lokal verwendeten Request anlegen:

```sh
LAB_ID="manual-$(date +%s)"
curl -sS -X POST http://127.0.0.1:15729/webhook/ch29-propose \
  -H 'Content-Type: application/json' \
  --data "{\"request_id\":\"$LAB_ID\",\"case_id\":\"notice-standard\",\"tenant_id\":\"lab\",\"draft\":\"Synthetische Statusmeldung zu Vorgang 100: Prüfung abgeschlossen.\"}"
curl -sS "http://127.0.0.1:8129/state/$LAB_ID" | python3 -m json.tool
```

Der erste Aufruf liefert den unveränderlichen `proposal_hash`. Prüfen Sie im Status Ziel, Entwurf, Beleg-ID und Hash. Öffnen Sie danach [Fachfreigabe](http://127.0.0.1:15729/form/ch29-owner), tragen Sie Request-ID und Hash ein und entscheiden Sie mit der synthetischen Akteur-ID `alice`. Eine Freigabe führt zu `awaiting_reviewer`, **noch nicht** zum Outbox-Eintrag. Öffnen Sie dann [Zweitprüfung](http://127.0.0.1:15729/form/ch29-reviewer), prüfen Sie denselben Vorschlag und wählen Sie `bob` als andere Akteur-ID. Erst dann steht der Status auf `committed` und `outbox_count` auf `1`.

Alternativ kann bereits die erste Person `Deny` wählen; dann bleibt `outbox_count=0`. Die zweite Person kann ebenfalls ablehnen. Das Timeout-Fixture `notice-timeout` setzt nach der ersten Freigabe eine Sekunde Frist. Danach darf ein separater Aufruf an `POST /webhook/ch29-escalate` mit `role=escalation`, `actor_id=carol`, `decision=Approve`, Request-ID, Mandant und Hash die zweite Prüfung ersetzen. Eine Eskalation ohne vorherige erste Freigabe ist nicht zulässig. Die Live-Prüfung führt diesen Pfad automatisch aus.

## Was der Vertrag tatsächlich schützt

Der Entwurf muss exakt zum synthetischen Fall passen; der Dienst speichert einen kanonischen Vorschlag samt SHA-256-Hash. Jede Entscheidung bindet sich an diesen Hash und an die Phase. `commit` liest nur den gespeicherten Vorschlag, nicht einen neuen Entwurf aus dem Aufruf. SQLite-Transaktionen serialisieren gleichzeitige Entscheidungen; der eindeutige Outbox-Schlüssel und der Status verhindern einen zweiten Schreibeffekt. Die Audit-Zeilen dokumentieren Übergänge, sind aber weder signiert noch gegen einen Datenbankadministrator manipulationssicher.

Für Produktion fehlen insbesondere echte Identitäts- und Rollenprüfung, Zugriffsschutz für Gate und Status-API, abgesicherte Review-Kanäle, überprüfte Downstream-Berechtigungen, anwendungsübergreifende Idempotenz und manipulationsgeschützte Protokollierung. n8n Form Trigger kann laut Dokumentation mit n8n User Auth betrieben werden; dieses offene Loopback-Lehrlabor nutzt diese Funktion bewusst nicht.

## Aufräumen

```sh
make ch29-down
```

Das entfernt nur die Kapitel-29-Container und das Kapitelnetz. Die eigenen Datenvolumes bleiben erhalten; neue manuelle Läufe brauchen daher eine neue Request-ID.
