# Kapitel 10 – Robuste Workflows

Eigenständiges, ausschließlich lokales Labor mit n8n 2.40.7, PostgreSQL und
einem Python-3.12-Dienst. Alle Dokumente sind synthetisch. Die nach außen
sichtbaren Ports sind auf `127.0.0.1` begrenzt. Das Labor hat weder
Authentifizierung noch TLS und darf nicht ins Netz gestellt werden.

## Start und Prüfung

Voraussetzungen: Docker Desktop mit Compose, Python 3 und `uv`.

```sh
cd code/ch10
python3 init_env.py
uv sync --locked
uv run --locked pytest -q
python3 build_workflows.py
docker compose config --quiet
docker compose up -d --build --wait
uv run --locked python verify_live.py --prepare
```

`init_env.py` erzeugt `.env` einmalig mit Dateimodus 0600 und überschreibt
sie nicht. Die Datei ist nicht für Git bestimmt. Der Live-Test importiert und
veröffentlicht beide Workflows. Dafür wird nur die Kapitel-10-n8n-Instanz
kurz gestoppt und wieder gestartet. Auch ohne `--prepare` startet der Test
n8n einmal während einer wartenden Freigabe neu und prüft deren Fortsetzung.
Vorhandene offene Freigabefälle sollten vorher beendet werden. `--prepare`
ist bei einem erneuten Test ohne geänderte Workflow-Dateien nicht erforderlich.

Das n8n-Frontend ist unter `http://127.0.0.1:15684` erreichbar. Der lokale
Zustandsdienst läuft unter `http://127.0.0.1:18070`. Ein Beispielauftrag:

```sh
LAB_ID="manual-$(date +%s)"
curl -sS -X POST http://127.0.0.1:15684/webhook/ch10-document \
  -H 'Content-Type: application/json' \
  --data "{\"doc_id\":\"$LAB_ID\",\"content\":\"Synthetischer Text\",\"scenario\":\"clean\"}"
sleep 2
curl -sS "http://127.0.0.1:18070/state/$LAB_ID"
```

Die erste Antwort bestätigt nur den **Start** des Workflows. Die Verarbeitung
läuft asynchron: Eine sofortige Statusabfrage kann noch `404` mit
`not_found` liefern. In diesem Fall nach einigen Sekunden erneut abfragen.
Der Status zeigt dann `awaiting_approval` und eine lokale `approval_url`; diese URL
im Browser öffnen und `Approve` oder `Deny` wählen. Eine wiederverwendete
`doc_id` mit anderem Inhalt ergibt `409 idempotency_conflict`. Für weitere
Versuche immer eine neue synthetische ID verwenden.

## Szenarien und erwartete Zustände

| `scenario` | Analyse | Erwarteter Endzustand |
| --- | --- | --- |
| `clean` | 200 beim ersten Versuch | Freigabe, dann `published` oder `denied` |
| `transient` | erst 503, dann 200 | Freigabe, danach `published` |
| `permanent` | 422 | `quarantined`, ein Versuch |
| `always_transient` | dreimal 503 | `quarantined`, drei Versuche |
| `timeout_after_commit` | Analyse 200; erste Publish-Antwort verspätet | `published`, zwei Publish-Aufrufe, ein Effekt |
| `unexpected` | 500 | fehlgeschlagene n8n-Ausführung, ein zentraler Alarm |

Ein unbekannter `scenario`-Wert wird mit 400 abgelehnt und als fehlgeschlagene
Ausführung alarmiert. Ein geänderter Inhalt unter derselben `doc_id` ergibt
409; der Aufrufer muss Auftrag und Schlüssel fachlich klären.

Der produktionsnahe Retry-/Idempotenzvertrag liegt in `contract.py`; die
Fehler sind in `service.py` deterministisch injiziert. Der Alarm-Workflow
speichert nur einen Alarm je n8n-Ausführung. Quarantäne ist hier eine
SQLite-Zustandsablage, keine echte Dead-Letter-Queue. Die lokale
Freigabe-URL ist ohne Identitätsprüfung nutzbar und dient ausschließlich dem
didaktischen Integrationstest.

## Ende des Labors

```sh
docker compose stop
```

Die Volumes bleiben dabei erhalten. `docker compose down --volumes` würde
den Laborzustand und die n8n-Ausführungen löschen und ist nur sinnvoll,
wenn diese Daten bewusst nicht mehr benötigt werden.
