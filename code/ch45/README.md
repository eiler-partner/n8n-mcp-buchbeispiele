# Kapitel 45: eigenständige Compliance- und Dokumentenprüfung

Das Labor ist eine **technische Demonstration**, keine Rechtsberatung,
Konformitätsbescheinigung oder automatische Anwendbarkeitsentscheidung. Die
Kontrollformulierungen sind synthetische interne Regeln. DORA und AI Act sind
versionierte amtliche Quellenanker, deren Geltung und aktuelle Fassung eine
Fachperson prüfen muss. Alle Dokumente und Personen sind erfunden.

```sh
make ch45-verify
make ch45-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf
räumt sein Compose-Projekt selbst ab; `make ch45-down` (im Kapitelordner
`make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort
von Hand gestartet haben, etwa beim manuellen Durchspielen unten.

Der erste Lauf prüft Parser, MCP Resources, Belege, Status, Freigabe, Audit und
Negativfälle ohne Docker. Der zweite startet einen frischen, nur diesem
Kapitel zugeordneten Compose-Stack, ruft den veröffentlichten n8n-Webhook
für Entwurf, Review und Export auf und entfernt **nur sein temporäres**
Projekt und die dazugehörigen Volumes. Er benötigt weder Internetzugriff zur
Laufzeit noch bezahlte API, Modell-Download oder frühere Kapitelcontainer.
Die Beobachtung steht in `reports/live-observation.json`.

Erwartet: sechs Kontrollen; `C01` und `C05` erfüllt, `C02` und `C06`
teilweise erfüllt, `C03` nicht belegt und `C04` als nur vorgeschlagenes
„nicht anwendbar“. Bei `C06` bleibt ein Widerspruch zwischen 30 und 90 Tagen
sichtbar. Vier offene Kontrollen müssen bei Freigabe ausdrücklich benannt
werden. Vor Freigabe, nach Ablehnung, bei Selbstfreigabe oder veralteter
Prüfgrundlage gibt es keinen Export.

Optional mit bereits installiertem Ollama-Modell:

```sh
CH45_OLLAMA_MODEL=qwen3:14b make ch45-ollama
```

Im Kapitelordner gleichwertig: `CH45_OLLAMA_MODEL=qwen3:14b make ollama`.

Der Modelltext ist ausschließlich eine datierte, nicht veröffentlichte
Prüfnotiz. Er ändert keinen Status und erteilt keine Freigabe.

Für ein manuelles lokales Durchspielen: `CH45_SIGNING_KEY` mit mindestens 32
zufälligen Zeichen exportieren, `docker compose up -d --build --wait` starten,
mit `python token_cli.py requester alice` und `python token_cli.py reviewer bob`
getrennte, kurzlebige Tokens erzeugen und JSON-Aufträge an
`http://127.0.0.1:15745/webhook/ch45-review` senden. Danach in
derselben Shell (mit gesetztem `CH45_SIGNING_KEY`) im Wurzelverzeichnis
`make ch45-down` ausführen (im Kapitelordner `make down`);
das belässt die Volumes für eine spätere Sichtung.

Grenzen: Die Identitäten sind lokale HMAC-Fixtures, nicht ein produktiver IdP.
Der Dienst verwendet SQLite und eine HMAC-Ereigniskette, kein externes
revisionssicheres Archiv. n8n erhält in diesem Lernlabor die Token im
Anfragekörper; in Produktion wären ein authentisierter Zugang, kurzlebige
Header-Credentials, getrennte Rollen, persistente Retention/Legal Hold,
Schlüsselverwaltung, Egress- und Datenklassifikationskontrollen erforderlich.
