# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch43-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down
test:
	$(PYTHON) -m unittest discover -s tests -v
live:
	$(PYTHON) verify_live.py
ollama:
	$(PYTHON) verify_ollama.py
down:
	@echo "verify_live.py startet eigene Compose-Projekte und raeumt sie selbst ab."
	CH43_SIGNING_KEY=unused-for-down docker compose down --remove-orphans
