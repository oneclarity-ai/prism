# 03 — Environment Setup

## Install

| Tool | Version | Used for |
| --- | --- | --- |
| Python | 3.12+ | backend, worker |
| uv | latest | Python packages and virtualenv |
| Node.js | 20 LTS or 22 LTS | frontend, Playwright MCP server |
| pnpm | 9+ | frontend packages |
| Docker Desktop | latest | Postgres, sandbox browser, eval app |
| Git | latest | source control |

## Accounts and keys

| Key | Where it goes | Notes |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | `backend/.env` | e.g. `https://<resource>.openai.azure.com` |
| `AZURE_OPENAI_API_KEY` | `backend/.env` | Or use Entra ID auth later |
| `AZURE_OPENAI_API_VERSION` | `backend/.env` | API version enabled on your resource |
| `AZURE_OPENAI_DEPLOYMENT` | `backend/.env` | Deployment name of the chat model used by the QA agent |
| `GITHUB_TOKEN` (fine-grained, issues:write on test repo only) | stored as a secret in the app, not in `.env` for production | For bug filing (milestone 4) |
| `JIRA_*` (optional) | secret | Only if Jira is used instead of GitHub Issues |

Never commit `.env`. Add `.env.example` with empty values.

## Steps

1. Create the repo `oneclarity-qa/` with `backend/`, `frontend/`, `sandbox/`, `eval-app/`, `docs/`.
2. `docker compose up -d postgres` (see 04 for the compose file).
3. Backend: `cd backend && uv init && uv add fastapi uvicorn[standard] pydantic-settings sqlalchemy[asyncio] asyncpg alembic structlog apscheduler openai-agents httpx`.
4. Dev tools: `uv add --dev pytest pytest-asyncio ruff mypy`.
5. In the Azure portal, deploy a chat model that supports tool calling and note the deployment name and API version.
6. Playwright MCP: confirm `npx @playwright/mcp@latest --help` runs; then build it into `sandbox/` (see 07).
7. Frontend: `pnpm create vite frontend --template react-ts` (see 11).
8. Add `pre-commit` with ruff (Python) and eslint/prettier (TS).

## Done when

- `docker compose ps` shows Postgres healthy.
- `uv run python -c "import agents"` succeeds and a one-line test call to the Azure deployment returns text.
- `pnpm dev` in `frontend/` opens the Vite page.
