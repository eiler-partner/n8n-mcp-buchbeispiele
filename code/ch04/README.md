# Kapitel 4: Das reproduzierbare Lernlabor

Das Profil ist ausschließlich für den lokalen Lernbetrieb gedacht. Es startet
n8n 2.40.7 und PostgreSQL 17.11 auf einem privaten Compose-Netz. Nur n8n wird
an die Loopback-Adresse des Hosts veröffentlicht. Das Ollama-Profil ist optional
und in Docker Desktop auf Apple Silicon CPU-basiert.

## Erster Start

Voraussetzungen: Docker Engine mit Compose v2; Python 3.12 und uv für Tests.

1. In dieses Verzeichnis wechseln: `cd code/ch04`.
2. `python3 init_env.py` ausführen. Die lokale `.env` wird mit
   zwei unabhängigen Zufallswerten und restriktiven Dateirechten erzeugt.
3. `docker compose config --quiet` prüft die Konfiguration.
4. `docker compose up -d --wait` startet das Profil.
5. `uv run --locked python smoke.py` prüft n8n, PostgreSQL und Version.
6. `http://127.0.0.1:15678` im Browser öffnen und ein lokales
   Eigentümerkonto anlegen. Die Registrierung zur Registered Community Edition
   ist optional.

Die eingecheckte `uv.lock` fixiert die Testabhängigkeiten;
Leser verwenden `--locked`.

## Optionale Wege

* Ollama-Container (CPU): `docker compose --profile ollama up -d --wait`.
  Modelle werden nicht automatisch geladen; der Endpunkt ist nur lokal
  unter Port 11434 erreichbar. Auf Apple Silicon ist eine nativ laufende
  Ollama-App häufig geeigneter. Dann **nicht** das Compose-Profil starten.
  n8n-Container erreichen den Host über `host.docker.internal:11434`.
* n8n Cloud: Die Compose-Schritte entfallen. Python-Tests bleiben lokal
  möglich; der lokale Smoke-Test für n8n/PostgreSQL ist dort nicht anwendbar.

## Diagnose und Rücksetzung

`docker compose ps` und `docker compose logs --tail=80 n8n postgres`
zeigen Status und Startfehler. Host-Port 15678 ist bei Bedarf in `.env`
(`LAB_N8N_HOST_PORT`) änderbar. Nach der Änderung `docker compose up -d --wait` erneut
ausführen.

`docker compose down` stoppt Container und Netz, **behält die drei
benannten Volumes**. Ein vollständiger Reset ist absichtlich kein
Ein-Zeilen-Standardbefehl: Erst Daten und Schlüssel sichern, dann im
Verzeichnis `code/ch04` gezielt `docker compose down --volumes`
ausführen. Nur die Volumes dieses Compose-Projekts werden entfernt.
Die bestehende `.env` bleibt dabei erhalten; `init_env.py`
überschreibt sie nie. Zum echten Neuaufbau Schlüssel bewusst neu erzeugen
oder die gesicherte `.env` zusammen mit Daten wiederherstellen.

## Prüfungen

`uv run --locked python -m pytest -q` prüft Generierung, Portfehler und
Compose-Vertrag ohne laufende Container.
