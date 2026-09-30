# Kapitel 40: ein Request, vier Schichten

`make ch40-verify` prüft Kosten-, SLI- und Korrelationsverträge ohne Docker.
`make ch40-live` startet einen **eigenen**, kurzlebigen Compose-Stack mit n8n,
PostgreSQL und Python-Fixtures. Der Test entfernt am Ende nur diesen Stack samt
synthetischem Datenbank-Volume. Andere Kapitel-Stacks bleiben unberührt.
Beide Befehle werden im Wurzelverzeichnis des Begleitmaterials aufgerufen; im
Kapitelordner gelten gleichwertig `make test` und `make live`. `make ch40-down`
(im Kapitelordner `make down`) ist nur eine Sicherheitsleine für einen
Kapitel-Stack, den Sie dort von Hand gestartet haben. Einen Ollama-Lauf hat
Kapitel 40 nicht.

Der Live-Pfad ist n8n-Webhook → HTTP-Bridge → echte MCP-stdio-Sitzung
(`initialize`, `tools/list`, `tools/call`) → Retrieval-/Modell-Fixtures. Die
Bridge ist eine Laboradaption, **kein** n8n-MCP-Client-Node und kein vollständiger
MCP-Transport-Compliance-Test. Anwendungsereignisse sind **keine** nativen OTel-Spans.
Ein zweiter Request verliert gezielt seine Modell-Korrelation, ein dritter
simuliert einen Modellfehler. Beide zählen im SLI als schlecht. Kosten basieren
auf einem frei erfundenen Lehrtarif, nicht auf Anbieterpreisen.

Ports 15741 und 8140 sind nur an Loopback gebunden. Das Labor hat kein TLS und
keine Authentisierung; nur synthetische Eingaben verwenden. Der Metrikendpunkt
von n8n darf nicht öffentlich zugänglich sein. Der datierte Bericht landet in
`reports/live-observation.json`.
