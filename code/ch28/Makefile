# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch28-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down report ollama-live
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
live:
	docker compose up -d --build --wait
	PYTHONPATH=src $(PYTHON) verify_live.py
ollama:
	PYTHONPATH=src $(PYTHON) -m ch28_lab.cli ollama-live
down:
	docker compose down --remove-orphans
report:
	PYTHONPATH=src $(PYTHON) -m ch28_lab.cli report
ollama-live: ollama
