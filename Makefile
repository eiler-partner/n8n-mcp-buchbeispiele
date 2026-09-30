# Begleitmaterial zu "n8n & MCP Engineering" (Band 1 und Band 2)
# Alle Befehle im Wurzelverzeichnis dieses Repositorys ausfuehren.
#   make chNN-verify   schnelle Tests ohne Docker
#   make chNN-live     Docker-/n8n-Labor (wo vorhanden)
#   make chNN-ollama   optionaler Lauf mit installiertem Ollama-Modell (Band 2)
#   make chNN-down     Container des Kapitels stoppen (Band 2)
#   make verify-all    Offline-Pruefungen aller Labore von Band 1
#   make verify-band2  Offline-Pruefungen aller Labore von Band 2
SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help verify-all ch01-verify ch02-verify ch03-verify ch04-verify ch05-verify ch06-verify ch07-verify ch08-verify ch09-verify ch10-verify ch11-verify ch12-verify ch13-verify ch14-verify ch15-verify ch16-verify ch17-verify ch18-verify ch19-verify ch20-verify ch21-verify ch22-verify ch23-verify ch24-verify ch24-test ch25-verify ch25-live ch26-verify ch26-live ch27-verify ch27-live ch28-verify ch28-live ch29-verify ch29-live ch30-verify ch30-live ch31-verify ch31-live ch32-verify ch32-live ch33-verify ch33-live ch34-verify ch34-live ch35-verify ch35-live ch36-verify ch36-live ch37-verify ch37-live ch38-verify ch38-live ch39-verify ch39-live ch40-verify ch40-live ch41-verify ch41-live ch42-verify ch42-live ch43-verify ch43-live ch44-verify ch44-live ch45-verify ch45-live ch10-live ch11-live ch13-live ch14-live ch15-live ch16-live ch25-ollama ch25-down ch26-ollama ch26-down ch27-ollama ch27-down ch28-ollama ch28-down ch29-ollama ch29-down ch30-ollama ch30-down ch31-ollama ch31-down ch32-ollama ch32-down ch33-ollama ch33-down ch34-ollama ch34-down ch35-ollama ch35-down ch36-ollama ch36-down ch37-ollama ch37-down ch38-ollama ch38-down ch39-ollama ch39-down ch40-ollama ch40-down ch41-ollama ch41-down ch42-ollama ch42-down ch43-ollama ch43-down ch44-ollama ch44-down ch45-ollama ch45-down verify-band2

help:
	@sed -n '1,8p' $(firstword $(MAKEFILE_LIST)) | sed 's/^# \{0,1\}//'

# ---------------------------------------------------------------------------
# Laborpruefungen
#   chNN-verify  schnelle Pruefung ohne Docker (Unit- und Vertragstests)
#   chNN-live    Lauf gegen den laufenden Docker-Stack des Kapitels
#   verify-all   alle 24 chNN-verify nacheinander; bricht beim ersten Fehler ab
#   ch24-verify  vollstaendiger Integrationslauf mit Docker (Kapitel 24)
# ---------------------------------------------------------------------------
VERIFY_ALL := $(foreach n,01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23,ch$(n)-verify) ch24-test

verify-all: $(VERIFY_ALL)
	@echo "verify-all: alle 24 Laborpruefungen bestanden"

verify-band2: ch25-verify ch26-verify ch27-verify ch28-verify ch29-verify ch30-verify ch31-verify ch32-verify ch33-verify ch34-verify ch35-verify ch36-verify ch37-verify ch38-verify ch39-verify ch40-verify ch41-verify ch42-verify ch43-verify ch44-verify ch45-verify
	@echo "verify-band2: alle 21 Offline-Pruefungen von Band 2 bestanden"

ch01-verify:
	python3 -m unittest discover -s code/ch01/tests -v

ch02-verify:
	python3 code/ch02/validate.py code/ch02/architecture.json
	python3 -m unittest discover -s code/ch02/tests -v

ch03-verify:
	uv run --no-project --with jsonschema==4.26.0 python -m unittest discover -s code/ch03/tests -v

ch04-verify:
	cd code/ch04 && uv run --locked python -m pytest -q

ch05-verify:
	python3 -m unittest discover -s code/ch05/tests -v

ch06-verify:
	python3 -m unittest discover -s code/ch06/tests -v

ch07-verify:
	python3 -m unittest discover -s code/ch07/tests -v

ch08-verify:
	python3 -m unittest discover -s code/ch08/tests -v

ch09-verify:
	cd code/ch09 && UV_CACHE_DIR=/tmp/buch-ch09-uv-cache uv run --locked pytest -q

ch10-verify:
	cd code/ch10 && UV_CACHE_DIR=/tmp/buch-ch10-uv-cache uv run --locked pytest -q

ch10-live:
	cd code/ch10 && UV_CACHE_DIR=/tmp/buch-ch10-uv-cache uv run --locked python verify_live.py --prepare

ch11-verify:
	python3 -m unittest discover -s code/ch11/tests -v

ch11-live:
	cd code/ch11 && python3 init_env.py && python3 build_workflows.py && python3 verify_live.py

ch12-verify:
	cd code/ch12 && UV_CACHE_DIR=/tmp/buch-ch12-uv-cache uv run --locked pytest -q

ch13-verify:
	python3 -m unittest discover -s code/ch13/tests -v
	python3 code/ch13/validate_decisions.py

ch13-live:
	cd code/ch13 && docker compose up -d --build --wait && python3 verify_live.py

ch14-verify:
	cd code/ch14 && UV_CACHE_DIR=/tmp/buch-ch14-uv-cache uv run --locked pytest -q

ch14-live:
	cd code/ch14 && docker compose run --build --rm wire-lab

ch15-verify:
	cd code/ch15 && UV_CACHE_DIR=/tmp/buch-ch15-uv-cache uv run --locked pytest -q

ch15-live:
	cd code/ch15 && docker compose run --build --rm primitives-lab

ch16-verify:
	cd code/ch16 && UV_CACHE_DIR=/tmp/buch-ch16-uv-cache uv run --locked pytest -q

ch16-live:
	cd code/ch16 && docker compose run --build --rm transport-lab

ch17-verify:
	cd code/ch17 && UV_CACHE_DIR=/tmp/buch-ch17-uv-cache uv run --locked pytest -q

ch18-verify:
	cd code/ch18 && UV_CACHE_DIR=/tmp/buch-ch18-uv-cache uv run --locked pytest -q

ch19-verify:
	cd code/ch19 && UV_CACHE_DIR=/tmp/buch-ch19-uv-cache uv run --locked pytest -q

ch20-verify:
	cd code/ch20 && UV_CACHE_DIR=/tmp/buch-ch20-uv-cache uv run --locked pytest -q

ch21-verify:
	cd code/ch21 && UV_CACHE_DIR=/tmp/buch-ch21-uv-cache uv run --locked pytest -q

ch22-verify:
	cd code/ch22 && UV_CACHE_DIR=/tmp/buch-ch22-uv-cache uv run --locked pytest -q

ch23-verify:
	cd code/ch23 && UV_CACHE_DIR=/tmp/buch-ch23-uv-cache uv run --locked pytest -q

ch24-test:
	$(MAKE) -C code/ch24 test

ch25-verify:
	$(MAKE) -C code/ch25 test

ch25-live:
	$(MAKE) -C code/ch25 live

ch25-ollama:
	$(MAKE) -C code/ch25 ollama

ch25-down:
	$(MAKE) -C code/ch25 down

ch26-verify:
	$(MAKE) -C code/ch26 test

ch26-live:
	$(MAKE) -C code/ch26 live

ch26-ollama:
	$(MAKE) -C code/ch26 ollama

ch26-down:
	$(MAKE) -C code/ch26 down

ch27-verify:
	$(MAKE) -C code/ch27 test

ch27-live:
	$(MAKE) -C code/ch27 live

ch27-ollama:
	$(MAKE) -C code/ch27 ollama

ch27-down:
	$(MAKE) -C code/ch27 down

ch28-verify:
	$(MAKE) -C code/ch28 test

ch28-live:
	$(MAKE) -C code/ch28 live

ch28-ollama:
	$(MAKE) -C code/ch28 ollama

ch28-down:
	$(MAKE) -C code/ch28 down

ch29-verify:
	$(MAKE) -C code/ch29 test

ch29-live:
	$(MAKE) -C code/ch29 live

ch29-ollama:
	$(MAKE) -C code/ch29 ollama

ch29-down:
	$(MAKE) -C code/ch29 down

ch30-verify:
	$(MAKE) -C code/ch30 test

ch30-live:
	$(MAKE) -C code/ch30 live

ch30-ollama:
	$(MAKE) -C code/ch30 ollama

ch30-down:
	$(MAKE) -C code/ch30 down

ch31-verify:
	$(MAKE) -C code/ch31 test

ch31-live:
	$(MAKE) -C code/ch31 live

ch31-ollama:
	$(MAKE) -C code/ch31 ollama

ch31-down:
	$(MAKE) -C code/ch31 down

ch32-verify:
	$(MAKE) -C code/ch32 test

ch32-live:
	$(MAKE) -C code/ch32 live

ch32-ollama:
	$(MAKE) -C code/ch32 ollama

ch32-down:
	$(MAKE) -C code/ch32 down

ch33-verify:
	$(MAKE) -C code/ch33 test

ch33-live:
	$(MAKE) -C code/ch33 live

ch33-ollama:
	$(MAKE) -C code/ch33 ollama

ch33-down:
	$(MAKE) -C code/ch33 down

ch34-verify:
	$(MAKE) -C code/ch34 test

ch34-live:
	$(MAKE) -C code/ch34 live

ch34-ollama:
	$(MAKE) -C code/ch34 ollama

ch34-down:
	$(MAKE) -C code/ch34 down

ch35-verify:
	$(MAKE) -C code/ch35 test

ch35-live:
	$(MAKE) -C code/ch35 live

ch35-ollama:
	$(MAKE) -C code/ch35 ollama

ch35-down:
	$(MAKE) -C code/ch35 down

ch36-verify:
	$(MAKE) -C code/ch36 test

ch36-live:
	$(MAKE) -C code/ch36 live

ch36-ollama:
	$(MAKE) -C code/ch36 ollama

ch36-down:
	$(MAKE) -C code/ch36 down

ch37-verify:
	$(MAKE) -C code/ch37 test

ch37-live:
	$(MAKE) -C code/ch37 live

ch37-ollama:
	$(MAKE) -C code/ch37 ollama

ch37-down:
	$(MAKE) -C code/ch37 down

ch38-verify:
	$(MAKE) -C code/ch38 test

ch38-live:
	$(MAKE) -C code/ch38 live

ch38-ollama:
	$(MAKE) -C code/ch38 ollama

ch38-down:
	$(MAKE) -C code/ch38 down

ch39-verify:
	$(MAKE) -C code/ch39 test

ch39-live:
	$(MAKE) -C code/ch39 live

ch39-ollama:
	$(MAKE) -C code/ch39 ollama

ch39-down:
	$(MAKE) -C code/ch39 down

ch40-verify:
	$(MAKE) -C code/ch40 test

ch40-live:
	$(MAKE) -C code/ch40 live

ch40-ollama:
	$(MAKE) -C code/ch40 ollama

ch40-down:
	$(MAKE) -C code/ch40 down

ch41-verify:
	$(MAKE) -C code/ch41 test

ch41-live:
	$(MAKE) -C code/ch41 live

ch41-ollama:
	$(MAKE) -C code/ch41 ollama

ch41-down:
	$(MAKE) -C code/ch41 down

ch42-verify:
	$(MAKE) -C code/ch42 test

ch42-live:
	$(MAKE) -C code/ch42 live

ch42-ollama:
	$(MAKE) -C code/ch42 ollama

ch42-down:
	$(MAKE) -C code/ch42 down

ch43-verify:
	$(MAKE) -C code/ch43 test

ch43-live:
	$(MAKE) -C code/ch43 live

ch43-ollama:
	$(MAKE) -C code/ch43 ollama

ch43-down:
	$(MAKE) -C code/ch43 down

ch44-verify:
	$(MAKE) -C code/ch44 test

ch44-live:
	$(MAKE) -C code/ch44 live

ch44-ollama:
	$(MAKE) -C code/ch44 ollama

ch44-down:
	$(MAKE) -C code/ch44 down

ch45-verify:
	$(MAKE) -C code/ch45 test

ch45-live:
	$(MAKE) -C code/ch45 live

ch45-ollama:
	$(MAKE) -C code/ch45 ollama

ch45-down:
	$(MAKE) -C code/ch45 down

ch24-verify:
	$(MAKE) -C code/ch24 verify
