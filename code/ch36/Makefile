# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch36-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down report
test:
	$(PYTHON) -m unittest discover -s tests -v
live:
	docker compose up -d --build --wait
	$(PYTHON) verify_live.py
ollama:
	$(PYTHON) verify_ollama.py
down:
	docker compose down --remove-orphans
report:
	$(PYTHON) evaluate.py
