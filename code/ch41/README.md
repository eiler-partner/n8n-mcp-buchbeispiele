# Kapitel 41: schreibendes Tool unter Sicherheitsreview

Der Pflichtpfad verwendet nur synthetische Daten, n8n, PostgreSQL und ein Python-Gate. Er benötigt keinen Cloud-Schlüssel und keinen Modell-Download.

```sh
make ch41-verify
make ch41-live
```

Im Kapitelordner gelten gleichwertig `make test` und `make live`. Der Live-Lauf räumt sein Compose-Projekt selbst ab; `make ch41-down` (im Kapitelordner `make down`) ist nur eine Sicherheitsleine für einen Kapitel-Stack, den Sie dort von Hand gestartet haben. Einen Ollama-Lauf hat Kapitel 41 nicht.

Der Live-Lauf erzeugt kurzlebige Geheimnisse und ein eindeutiges Compose-Projekt, startet den Stack, sendet positive und negative Fälle **durch den n8n-Webhook** und baut nur diesen Stack samt seinen Volumes wieder ab. Der datierte, nicht-sensitive Befund steht in `reports/live-observation.json`. Feste Host-Ports sind `127.0.0.1:15742` und `127.0.0.1:8141`; belegte Ports vor dem Lauf freigeben, nicht fremde Container entfernen.

Das strukturierte `threat-register.json` hält für jeden Risikoeintrag Kontrolle, Owner, Evidenz und Restrisiko fest. Die schnellen Tests prüfen seine Vollständigkeit als Mindestvertrag; eine fachliche Reviewentscheidung ersetzt das nicht.

Das Labor ist kein produktiver Identitätsdienst: HMAC-Lehr-Tokens werden lokal aus Testschlüsseln erzeugt, der Gate-Evidence-Endpunkt ist nur über Loopback zugänglich, und der HTTP-Pfad hat kein TLS. Für Produktion OIDC/OAuth mit Audience-/Issuer-Prüfung, TLS, Netzgrenzen, persistentes und extern gesichertes Audit sowie geprüfte Aufbewahrungsregeln einsetzen. Eine `allow`-Entscheidung besagt nur, dass die hier kodierten Bedingungen erfüllt sind, nicht dass ein Text fachlich richtig oder rechtlich zulässig ist.
