# OneClarity Agent Platform

A control plane for an "army" of AI agents (QA first; Sales, Marketing and Support planned), organised along the company's org chart. Backend: FastAPI + PostgreSQL + OpenAI Agents SDK on Azure OpenAI. Backend only: the UI is Prism's dashboard (`apps/prism`).

## Start here

- **Developer setup and handover:** [docs/29-developer-setup.md](docs/29-developer-setup.md)
- All documentation: [docs/00-README.md](docs/00-README.md)
- What is next: [docs/28-roadmap.md](docs/28-roadmap.md)

## Quick start (macOS / Linux / WSL2)

```bash
./scripts/setup.sh      # Python env, databases, seed, backend/.env
# fill AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY in backend/.env
./scripts/dev.sh        # API :8080, worker, Demo Shop :4000
```

API login (used by Prism via `QA_SWARM_EMAIL`/`QA_SWARM_PASSWORD`): `admin@oneclarity.local` / `change-me-now`. API docs: http://localhost:8080/docs
