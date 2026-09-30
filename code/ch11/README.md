# Kapitel 11 – Tests, Zusammenarbeit und Versionskontrolle

Eigenständiges Community-taugliches Labor mit n8n 2.40.7 in zwei getrennten
Docker-Instanzen (`dev` und `test`). Alle Fälle sind erfunden; es gibt keine
Credentials, keine externe API und keine produktive Umgebung. Die Ports sind
auf `127.0.0.1` begrenzt. Das Labor darf nicht ins öffentliche Netz gestellt
werden. Die beiden lokalen n8n-Instanzen haben keine Anmeldung/TLS und dienen
nur diesem Test.

## Start und vollständige Prüfung

Voraussetzungen: Docker Desktop mit Compose, Python 3.9+ und Git.

```sh
cd code/ch11
python3 init_env.py
python3 build_workflows.py
python3 -m unittest discover -s tests -v
docker compose config --quiet
python3 verify_live.py
```

`init_env.py` legt `.env` einmalig mit Dateimodus 0600 an; vorhandene Werte
werden nicht überschrieben. Die Geheimnisse stehen nicht in Git. Das Skript
`verify_live.py` importiert und veröffentlicht die Baseline in Dev, prüft sie,
exportiert den echten n8n-Stand, wiederholt dies mit der Kandidatenversion,
erzeugt einen Git-Diff in einem temporären Repository und führt dort ein
`git revert` aus. Dann überträgt es die Kandidatenversion nach Test und
stellt dort die Baseline wieder her. Vor jedem Import/Publish wird nur die
betreffende Laborinstanz gestoppt und anschließend gesund gestartet.
Nach dem Neustart prüft ein Canary-Aufruf den tatsächlich antwortenden
Produktionswebhook; ein gesunder Prozess allein gilt nicht als Freigabe.

Erwartete Ausgabe:

```text
PASS Dev baseline: imported, published, tested, and exported
PASS Git review: only the rule changes; revert restores baseline
PASS Test promotion: candidate behaves as reviewed
PASS Test rollback: approved baseline behavior restored
```

Der echte Server-CLI-Export liegt in `.exchange/*.raw.json`; er ist bewusst
nicht für Git bestimmt. Er kann Instanzmetadaten enthalten. Die Dateien
`baseline.review.json`, `candidate.review.json` und `review.patch` enthalten
die reduzierte Reviewoberfläche. Diese Reduktion entfernt Laufzeitmetadaten,
ersetzt aber keine menschliche Prüfung auf Zugangsdaten oder personenbezogene
Werte. Ein kleiner Negativtest belegt, dass bekannte Credential- und
Auth-Felder abgewiesen werden. Neue oder unbekannte Feldformen müssen im
Review gesondert bewertet werden.

## Selbst lesen und ausprobieren

Die Änderung ist absichtlich klein: Ein synthetischer Score von 75 führt bei
Schwelle 80 zu `manual_review`, bei Schwelle 70 zu `approved`; 85 wird in
beiden Versionen genehmigt, 101 als ungültig zurückgewiesen. Den bereinigten
Git-Diff nach dem Live-Test ansehen:

```sh
git diff --no-index -- .exchange/baseline.review.json .exchange/candidate.review.json
```

Der Befehl gibt bei einem vorhandenen Unterschied Exitcode 1 zurück; das ist
hier erwartbar. Die gespeicherte Patch-Datei steht in `.exchange/review.patch`.
Nach dem Live-Test läuft Dev mit der Kandidatenversion auf
`http://127.0.0.1:15685`, Test mit der zurückgenommenen Baseline auf
`http://127.0.0.1:15686`.

Den entscheidenden Fall selbst an beide veröffentlichten Webhooks senden:

```sh
curl -sS -X POST http://127.0.0.1:15685/webhook/ch11-review \
  -H 'Content-Type: application/json' --data '{"case_id":"manual-dev","score":75}'
curl -sS -X POST http://127.0.0.1:15686/webhook/ch11-review \
  -H 'Content-Type: application/json' --data '{"case_id":"manual-test","score":75}'
```

Dev soll `approved`, Test nach der Rücknahme `manual_review` antworten.

## Ende des Labors

```sh
docker compose stop
```

Die Volumes und `.env` bleiben erhalten. `docker compose down --volumes`
würde den lokalen Laborzustand löschen und ist nicht Teil des regulären
Abschlusses.
