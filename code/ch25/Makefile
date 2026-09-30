# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch25-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down ollama-live
test:
	$(PYTHON) -m unittest discover -s tests -v
live:
	docker compose up -d --build --wait
	$(PYTHON) verify_live.py
ollama:
	PYTHONPATH=src $(PYTHON) -m ch25_lab.cli ollama-live --output reports/ollama-observation.json
down:
	docker compose down --remove-orphans
ollama-live: ollama
