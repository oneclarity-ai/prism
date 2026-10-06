PYTHON ?= python3.11
VENV ?= .venv

.PHONY: setup dev migrate test test-integration lint format format-check typecheck secrets audit check

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements-dev.txt

dev:
	$(VENV)/bin/uvicorn app.main:app --reload

migrate:
	$(VENV)/bin/alembic upgrade head

test:
	$(VENV)/bin/pytest -q

test-integration:
	RUN_DB_TESTS=1 $(VENV)/bin/pytest -q

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff format app tests

format-check:
	$(VENV)/bin/ruff format --check app tests

typecheck:
	$(VENV)/bin/mypy

secrets:
	$(VENV)/bin/python scripts/check_secrets.py

audit:
	$(VENV)/bin/pip-audit -r requirements.txt

check: lint format-check typecheck test secrets
