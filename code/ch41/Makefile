# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch41-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down
test:
	$(PYTHON) -m unittest discover -s tests -v
live:
	$(PYTHON) verify_live.py
ollama:
	@echo "Kapitel 41 hat keinen Ollama-Lauf."
down:
	@echo "verify_live.py startet eigene Compose-Projekte und raeumt sie selbst ab."
	docker compose down --remove-orphans
