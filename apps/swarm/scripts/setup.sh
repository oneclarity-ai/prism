#!/usr/bin/env bash
# One-time setup: Python env (backend/.venv), database, seed.
# Safe to run again.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_NAME="${DB_NAME:-oneclarity}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing '$1'. $2"; exit 1; }; }
need uv   "Install: brew install uv"
need psql "Install: brew install postgresql@16 && brew services start postgresql@16"
need python3 "Install: brew install python@3.12 (also used to serve the Demo Shop)"

echo "==> Backend: Python virtual env (backend/.venv)"
cd "$ROOT/backend"
uv sync

if [ ! -f .env ]; then
  echo "==> Creating backend/.env with fresh keys"
  JWT=$(uv run python -c "import secrets; print(secrets.token_urlsafe(48))")
  FERNET=$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  sed -e "s|^JWT_SECRET=$|JWT_SECRET=$JWT|" \
      -e "s|^SECRET_ENCRYPTION_KEY=$|SECRET_ENCRYPTION_KEY=$FERNET|" \
      -e "s|^AZURE_OPENAI_ENDPOINT=.*|AZURE_OPENAI_ENDPOINT=|" .env.example > .env
fi

echo "==> Database '$DB_NAME'"
pg_isready -q || { echo "Postgres is not running. Start it: brew services start postgresql@16"; exit 1; }
psql -lqt | cut -d '|' -f 1 | grep -qw "$DB_NAME" || createdb "$DB_NAME"
psql -lqt | cut -d '|' -f 1 | grep -qw "${DB_NAME}_test" || createdb "${DB_NAME}_test"   # used by pytest
uv run alembic upgrade head
uv run python -m app.db.seed

echo
echo "Setup done. Start the API and worker with:  ./scripts/dev.sh"
