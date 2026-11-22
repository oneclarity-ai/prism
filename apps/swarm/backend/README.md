# OneClarity backend

FastAPI API and run worker for the OneClarity agent platform. The first agent is the QA Agent. The build plan is in [`../docs`](../docs/00-README.md).

**New developer?** Follow [docs/29-developer-setup.md](../docs/29-developer-setup.md); `../scripts/setup.sh` does all of the steps below.

## Run locally (Postgres installed on the machine)

```bash
cd backend
cp .env.example .env            # then fill JWT_SECRET, SECRET_ENCRYPTION_KEY and AZURE_OPENAI_*
createdb oneclarity
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed     # creates org, admin user, QA agent
uv run uvicorn app.main:app --reload
```

- API docs: http://localhost:8080/docs
- Sign in with `POST /api/v1/auth/login` using `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` from `.env`. Change the password before sharing the instance.

Worker (separate terminal): `uv run python -m app.worker.main`

## Run with Docker

```bash
docker compose up --build       # from the project root
docker compose exec api python -m app.db.seed
```

## Check Azure OpenAI

Fill the four `AZURE_OPENAI_*` values in `.env`, then:

```bash
uv run python scripts/check_azure.py
```

It sends one short prompt through the OpenAI Agents SDK to your deployment and prints the reply and token counts.

## Tests

```bash
createdb oneclarity_test
uv run pytest
uv run ruff check .
```

Tests use the `oneclarity_test` database (override with `TEST_DATABASE_URL`) and recreate its tables on each run.

## Layout

```
app/
  main.py            FastAPI app factory
  core/              settings, logging (with secret redaction), errors, security
  db/                models, enums, session, seed
  schemas/           Pydantic request/response models
  services/          business logic (no SQL in routers)
  api/routers/       health, auth, agents, secrets, targets, tasks
  worker/            run worker: claims queued runs and executes them
  runtime/           agent runtimes (OpenAI Agents SDK on Azure, fake) and platform tools
  agents/<role>/     one folder per agent role: definition.py + SKILL.md (see app/agents/README.md)
alembic/             migrations
scripts/             check_azure.py
tests/
```

## Logs

- Console: readable, coloured lines (`LOG_JSON=false`), one `request` line per API call with method, path, status, time and request id.
- Files: `var/logs/api.log` and `var/logs/worker.log` (JSON, rotated at 10 MB × 5).
- Follow live: `tail -f var/logs/worker.log`. More in [`../docs/21-logging-and-debugging.md`](../docs/21-logging-and-debugging.md).
