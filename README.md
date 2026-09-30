# n8n- und MCP-Buchbeispiele

Begleitende, lokal ausführbare Beispiele zu den beiden Bänden über n8n, MCP, KI-Agenten und RAG.

## Inhalt

- `code/ch01` bis `code/ch24`: Beispiele zu Band 1.
- `code/ch25` bis `code/ch45`: Beispiele zu Band 2.

Jedes Kapitel besitzt eine eigene `README.md` mit Voraussetzungen, Start- und Prüfschritten. Öffne zuerst die Anleitung des gewünschten Kapitels. Die Labore sind eigenständig; starte nicht mehrere Docker-Compose-Labore gleichzeitig, ohne ihre Ports und Projektnamen zu prüfen.

## Sicher ausprobieren

Die Daten, Identitäten, Tokens und Dokumente in den Beispielen sind synthetische Lehrdaten. Dateien namens `.env.example` enthalten nur lokale Beispielwerte. Erzeuge bei Bedarf eine eigene `.env`, verwende für echte Systeme andere Geheimnisse und committe die `.env` niemals. Die Beispiele sind keine unverändert einsetzbare Produktionskonfiguration; prüfe insbesondere Netzwerkfreigaben, Berechtigungen, Aufbewahrung und Lizenzbedingungen der verwendeten Drittsoftware.

Erzeugte Berichte, Datenbanken, virtuelle Umgebungen und lokale `.env`-Dateien gehören nicht in dieses Repository. Der Buchsatz und die vollständigen Buch-PDFs sind ebenfalls nicht enthalten.

## Lizenz

Der hier veröffentlichte eigene Beispielcode und die dazugehörigen Laboranleitungen stehen unter der [MIT-Lizenz](LICENSE). Eingesetzte Pakete, Container-Images, Dienste und Standards behalten ihre jeweiligen eigenen Lizenzen und Nutzungsbedingungen.
