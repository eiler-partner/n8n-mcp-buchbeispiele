# Kapitel 42: Restore-Probe in getrennter Testumgebung

Der Pflichtpfad nutzt n8n 2.40.7, PostgreSQL 17.11 und synthetische Daten. Kein Modell-Download oder API-Schlüssel ist nötig.

```sh
make ch42-verify
make ch42-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf räumt sein Compose-Projekt selbst ab; `make ch42-down` (im Kapitelordner `make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort von Hand gestartet haben. Einen Ollama-Lauf hat Kapitel 42 nicht.

Der Live-Lauf belegt die Host-Loopback-Ports `15746` und `15747`. Er erzeugt kurzlebige Schlüssel und ein eindeutiges Compose-Projekt, sichert die **Quell-Datenbank** mit `pg_dump -Fc`, spielt sie in eine **andere PostgreSQL-Instanz** zurück und startet dort n8n. Der Quell-Stack bleibt während der Probe unverändert verfügbar. Nach dem Test baut das Skript ausschließlich seine eigenen Container und Volumes ab. Der Backup-Dump liegt nur im temporären Arbeitsspeicher des Testprozesses; der datierte, nicht-sensitive Befund steht in `reports/live-observation.json`.

Das Manifest bindet Dump-Digest, n8n-Image und Instanzschlüssel-Digest. Der Preflight weist fehlende/falsche Schlüssel und einen manipulierten Dump ab. Das beweist **nicht**, dass echte n8n-Credentials nach einem Restore entschlüsselt werden können. Dazu wäre ein gesonderter Credential-Smoke-Test nötig. Das Labor prüft einen logischen PostgreSQL-Snapshot, kein PITR und keine atomare Sicherung mehrerer externer Datenspeicher. RPO/RTO-Werte sind Messungen dieses einzelnen lokalen Laufs, keine Produktionsgarantie.
