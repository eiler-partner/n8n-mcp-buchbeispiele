# Kapitel 38: lokaler TLS-/Secret-/Runner-Stack

Eigenständiges Labor mit synthetischen Daten. Docker Desktop/Engine und Python
3.9+ werden benötigt; kein Modell-Download und kein API-Schlüssel. Der Stack
stellt **nur** `https://localhost:15738` auf der Loopback-Adresse bereit.
Eine lokale Caddy-CA wird für den Test benutzt und **nicht** in den
System-Trust-Store importiert. Das ist kein öffentliches Zertifikat und keine
Produktionsfreigabe.

Vom Projektverzeichnis aus:

```bash
make ch38-verify
make ch38-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf
räumt sein Compose-Projekt selbst ab; `make ch38-down` (im Kapitelordner
`make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort
von Hand gestartet haben. Einen Ollama-Lauf hat Kapitel 38 nicht.

Der Live-Befehl erzeugt drei zufällige Secret-Dateien unter einem privaten
temporären Verzeichnis, startet nur den Kapitel-38-Compose-Stack, verifiziert
TLS mit dem exportierten **öffentlichen** Root-Zertifikat, n8n mit externem
Python Task Runner, weitergeleitete Header und den SSE-Pfad. Anschließend
werden die temporären Kapitel-38-Container, Netze und Volumes entfernt und die
Secret-Dateien gelöscht. Die datierte Beobachtung liegt danach in
`reports/live-observation.json`; sie enthält keine Secretwerte.

Das Profil `probe` startet nur den synthetischen Python-SSE-Dienst. Dieser
ist **kein** MCP-Server; er prüft allein Transport-/Proxy-Eigenschaften.
Der n8n-Workflow enthält weder Credentials noch echte Daten. Für eine echte
Bereitstellung fehlen öffentlicher DNS/ACME-Pfad, Benutzer-/Webhook-
Authentisierung, zentraler Secret Store, Backup/Restore, Update- und
Incident-Prozess sowie Last- und Sicherheitsabnahme.

Forwarded-Header: Der Live-Test sendet gefälschte Werte
(`X-Forwarded-For: 203.0.113.66`, `X-Forwarded-Host: spoofed.example`,
`X-Forwarded-Proto: http`). Die `Caddyfile` setzt keine `trusted_proxies`,
also muss Caddy alle drei ignorieren. Erwartet an der Probe: `X-Forwarded-For`
ist genau eine IP-Adresse (die Docker-Gegenstelle) ohne den gefälschten Wert,
`X-Forwarded-Host` ist `localhost:15738` (Host-Header der Anfrage),
`X-Forwarded-Proto` ist `https`. `make ch38-verify` testet die Prüflogik
(`forwarded_findings` in `verify_live.py`) offline. Ein Fall mit
`trusted_proxies` ist nicht Teil des Labors; er bräuchte einen zweiten Listener
oder einen vorgeschalteten Proxy mit fester Adresse.
