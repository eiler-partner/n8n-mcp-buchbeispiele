# Einheitliche Laborziele (aus dem Wurzelverzeichnis: make ch26-verify, -live, -ollama, -down)
PYTHON ?= python3
.PHONY: test live ollama down ollama-live
test:
	UV_CACHE_DIR=/tmp/buch-ch26-uv-cache uv run --locked python -m unittest discover -s tests -v
live:
	docker compose up -d --build --wait
	UV_CACHE_DIR=/tmp/buch-ch26-uv-cache uv run --locked python verify_live.py
ollama:
	UV_CACHE_DIR=/tmp/buch-ch26-uv-cache uv run --locked ch26-lab ollama-live --output reports/ollama-observation.json
down:
	docker compose down --remove-orphans
ollama-live: ollama
