PYTHON ?= python3.11
VENV ?= .venv

.PHONY: setup dev migrate test test-integration test-e2e lint format format-check typecheck secrets audit check release-check frontend-install frontend-build frontend-dev frontend-check frontend-types

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements-dev.txt
	$(MAKE) frontend-install

# The dashboard (frontend/, React + Vite + TypeScript) builds into app/static, which the API serves at /dashboard/.
frontend-install:
	cd frontend && npm ci

frontend-build:
	cd frontend && npm run build

# Hot-reloading dashboard on :5173 proxying /api to the API on :8000 (run `make dev` too).
frontend-dev:
	cd frontend && npm run dev

frontend-check:
	cd frontend && npm run check

# Regenerate frontend/src/types/api.generated.ts from the FastAPI OpenAPI schema.
frontend-types:
	$(VENV)/bin/python scripts/export_openapi.py frontend/openapi.json
	cd frontend && npm run types

dev:
	@test -f app/static/index.html || $(MAKE) frontend-build
	$(VENV)/bin/uvicorn app.main:app --reload

migrate:
	$(VENV)/bin/alembic upgrade head

test:
	$(VENV)/bin/pytest -q

test-integration:
	RUN_DB_TESTS=1 $(VENV)/bin/pytest -q

# Browser journeys on a scratch schema with fake Graph and LLM; needs Google Chrome.
test-e2e:
	RUN_E2E=1 $(VENV)/bin/pytest -q tests/e2e

lint:
	$(VENV)/bin/ruff check .

format:
	$(VENV)/bin/ruff format app tests

format-check:
	$(VENV)/bin/ruff format --check app tests

typecheck:
	$(VENV)/bin/mypy

secrets:
	$(VENV)/bin/python ../../scripts/check_secrets.py

audit:
	$(VENV)/bin/pip-audit -r requirements.txt

check: lint format-check typecheck test secrets frontend-check

# Everything the v2.2 release gate runs automatically (browser tests: make test-e2e).
release-check: check test-integration audit
