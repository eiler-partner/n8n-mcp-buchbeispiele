# Kapitel 9: Natives Python und externer Task Runner

Eigenständiges Labor mit n8n und Runner 2.40.7, PostgreSQL 17.11,
synthetischen CSV-Daten und pandas 3.0.6. Nur der n8n-Port auf Loopback ist
veröffentlicht. Docker Compose v2, Python 3.12 oder 3.13 und uv sind nötig.

Im Verzeichnis code/ch09 ausführen:

    python3 init_env.py
    uv sync --locked
    uv run --locked pytest -q
    docker compose config --quiet
    docker compose up -d --build --wait
    uv run --locked python verify_live.py

Erwartet: elf lokale Tests und vier PASS-Zeilen für core/clean, core/dirty,
pandas/clean, pandas/dirty. Der Live-Test importiert und veröffentlicht
die Workflows bei jedem Lauf erneut. Im Browser liegt n8n unter
http://127.0.0.1:15683. Bei Bedarf ein lokales Owner-Konto einrichten.
Der Webhook besitzt nur für dieses Loopback-Labor keine Authentifizierung.
Kein Internet-Deployment und keine echten Kunden- oder Bestelldaten verwenden.

Die Webhooks erhalten CSV-Inhalt als Feld `csv_text` in einem JSON-Body;
es wird keine Datei hochgeladen. Ein Bestellschlüssel ist ab seinem ersten
Auftreten belegt, auch wenn diese Zeile andere Fehler enthält. Eine spätere
Zeile mit derselben ID wird als Duplikat markiert.

Die fachliche Logik liegt in profiler.py. Nach Änderungen:

    python3 build_workflows.py
    uv run --locked pytest -q

Der Generator bettet exakt diese Quelle in die zwei versionierten n8n-Workflows
ein. Die Runner-Importfreigaben stehen in runner-config.json. pandas läuft im
Runner-Image, nicht im n8n-Hauptcontainer. Die Freigabe transitiver Imports
ist für dieses Lehrbeispiel erforderlich, vergrößert aber die Vertrauensfläche.
Cloud-n8n kann in nativen Python-Code-Nodes derzeit keine Python-Bibliotheken
importieren; dieses Labor erfordert Self-Hosting.

Zum Anhalten `docker compose down` verwenden. Volumes und die private,
Git-ignorierte .env bleiben erhalten; `--volumes` gehört nicht zur normalen
Bereinigung.
