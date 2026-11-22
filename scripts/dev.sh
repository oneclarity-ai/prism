#!/usr/bin/env bash
# Launch Prism and the swarm API/worker from this monorepo. Prism is the only user-facing UI (port 8000).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
prism_root="$repo_root/apps/prism"
swarm_root="${SWARM_ROOT:-$repo_root/apps/swarm}"

if [[ -z "$swarm_root" || ! -f "$swarm_root/backend/app/main.py" ]]; then
  printf 'Swarm backend not found at %s (set SWARM_ROOT to override).\n' "$swarm_root" >&2
  exit 2
fi
if [[ ! -x "$prism_root/.venv/bin/uvicorn" ]]; then
  printf 'Prism virtual environment is missing. Run make setup first (from the repo root).\n' >&2
  exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
  printf 'The uv command is required for the swarm backend.\n' >&2
  exit 2
fi
if command -v lsof >/dev/null 2>&1; then
  for port in 8000 8080; do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | grep -q .; then
      printf 'Port %s is in use. Stop the existing Prism or swarm dev session before starting the unified workspace.\n' "$port" >&2
      exit 2
    fi
  done
fi

if [[ ! -f "$prism_root/app/static/index.html" ]]; then
  printf 'Building the Prism dashboard (first run)...\n'
  (cd "$prism_root" && make frontend-build)
fi

(cd "$swarm_root/backend" && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8080) &
swarm_api_pid=$!
(cd "$swarm_root/backend" && LOG_JSON=false uv run python -m app.worker.main) &
swarm_worker_pid=$!
(cd "$prism_root" && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
prism_api_pid=$!

cleanup() {
  kill "$prism_api_pid" "$swarm_worker_pid" "$swarm_api_pid" 2>/dev/null || true
  wait "$prism_api_pid" "$swarm_worker_pid" "$swarm_api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

printf 'Prism UI: http://127.0.0.1:8000/dashboard/\n'
printf 'Swarm API and worker are running internally. Press Ctrl+C to stop all three.\n'
wait
