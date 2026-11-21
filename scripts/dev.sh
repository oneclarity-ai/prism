#!/usr/bin/env bash
# Start everything for local development. Ctrl+C stops all of it.
#   API        http://localhost:8080/docs
#   UI         http://localhost:5173
#   Worker     runs agent tasks in the background
#   Demo Shop  http://localhost:4000  (practice app with seeded bugs)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && uv run uvicorn app.main:app --reload --port 8080) &
(cd "$ROOT/backend" && LOG_JSON=false uv run python -m app.worker.main) &
(cd "$ROOT/frontend" && npm run dev) &
python3 -m http.server 4000 --directory "$ROOT/eval-app/site" >/dev/null 2>&1 &

echo "API http://localhost:8080/docs · UI http://localhost:5173 · Demo Shop http://localhost:4000 · worker running (Ctrl+C stops all)"
wait
