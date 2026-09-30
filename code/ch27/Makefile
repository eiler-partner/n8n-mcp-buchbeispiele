# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch27-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
live:
	docker compose up -d --build --wait
	$(PYTHON) verify_live.py
ollama:
	@echo "Kapitel 27 hat keinen Ollama-Lauf."
down:
	docker compose down --remove-orphans
