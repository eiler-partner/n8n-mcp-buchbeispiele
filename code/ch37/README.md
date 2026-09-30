# Kapitel 37: Architekturentscheidung als überprüfbares Lehrlabor

Dieses Labor wählt **keine Produktionsarchitektur automatisch**. Es zeigt an
drei synthetischen Profilen, wie harte Ausschlüsse vor einer offen gelegten
Gewichtung geprüft werden. Alle Zahlen sind Lehrannahmen, keine Preise, SLAs
oder Sicherheitszertifikate. Es werden weder echte Dokumente noch Schlüssel
an eine Modell-API gesendet.

Im Repository-Root:

```bash
make ch37-verify           # schnelle Tests ohne Docker
make -C code/ch37 report   # Entscheidungsbericht ohne Docker
make ch37-live             # Docker-/n8n-Labor (baut, startet, prüft)
make ch37-down             # Container des Kapitels stoppen
```

Im Kapitelordner gelten gleichwertig `make test`, `make report`, `make live`
und `make down`. Einen Ollama-Lauf hat Kapitel 37 nicht.

`make ch37-live` startet einen eigenen Docker-Compose-Stack mit Python-Dienst,
PostgreSQL und n8n. Er verwendet nur die Loopback-Ports 8137 und 15737.
Die n8n- und Datenbank-Passwörter sind **nur** feste, synthetische
Laborwerte; sie dürfen nicht in produktive Umgebungen übernommen werden.
`make ch37-down` stoppt und entfernt die Container, belässt das Daten-Volume.

Beispiel für einen einzelnen Profilaufruf:

```bash
curl -sS -X POST http://127.0.0.1:15737/webhook/ch37-architecture \
  -H 'Content-Type: application/json' \
  --data '{"action":"profile","profile_id":"geteilte_ki"}'
```

Die Felder `eligible` und `exclusions` sind wichtiger als `score`. Ein
`needs_clarification`-Ergebnis bedeutet: Keine eindeutige zulässige Auswahl;
die offenen fachlichen oder vertraglichen Voraussetzungen sind zuerst zu klären.
Für ein reales Projekt müssen Data-Flow-Mapping, Vertragslage, Edition,
Bedrohungsmodell, Last-/Kostenmessung und Restore/Exit-Test gesondert erfolgen.
