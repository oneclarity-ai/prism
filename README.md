# Prism

Prism is a self-hosted management assistant for Microsoft Teams. It turns selected
one-to-one Teams conversations into structured updates, blockers, commitments,
follow-ups, management risks, and a daily manager brief while retaining an auditable
record of every automated action.

> **Project status:** pre-release. Prism is under active development and has not had an
> independent security audit. Automation is disabled by default; evaluate it in a
> non-production Microsoft tenant before using it with a real team.

## Why Prism exists

Team status is often spread across chat threads, verbal commitments, and private notes.
Prism provides a manager-controlled workflow that keeps those signals structured without
creating a separate employee-facing application. The manager chooses exactly which
directory users are in scope and explicitly starts or stops Teams automation.

## Capabilities

- Import active users from a Microsoft Entra ID tenant.
- Limit automation to explicitly selected managed people.
- Send Teams check-ins and process replies through Microsoft Graph webhooks.
- Track projects, tasks, blockers, commitments, escalations, and daily updates.
- Apply deterministic safety validation before AI-proposed state changes or messages.
- Preserve issue-scoped conversation evidence and organisational memory.
- Produce a five-section daily manager brief and send it through Microsoft Graph mail.
- Expose versioned FastAPI endpoints, OpenAPI documentation, and a local dashboard.
- Record Azure OpenAI token usage and configured cost estimates.

Prism uses delegated Microsoft permissions: messages and email are visibly sent from the
connected manager account. It is not a Teams bot or a multi-tenant SaaS service.

## Architecture

Prism is a Python 3.11 application built with FastAPI, SQLAlchemy, Alembic, PostgreSQL,
Microsoft Graph, and optional Azure OpenAI. The application serves both its JSON API and
static management dashboard. An optional in-process scheduler runs daily automation jobs.

See [ARCHITECTURE.md](ARCHITECTURE.md) for components, data flow, background processing,
and security boundaries.

## Requirements

- Python 3.11 or 3.12
- PostgreSQL 14 or newer
- GNU Make for the documented convenience commands, or the equivalent commands directly
- A Microsoft Entra ID app registration for Teams automation
- A public HTTPS endpoint for Microsoft Graph change notifications
- Azure OpenAI only if LLM-backed reply analysis is enabled

Docker Engine with Compose can replace the local Python and PostgreSQL requirements.

## Quick start

```bash
git clone https://github.com/oneclarity-ai/prism.git
cd prism
cp .env.example .env
make setup
```

Create a local PostgreSQL database and update `DATABASE_URL` in `.env`:

```bash
createuser --pwprompt prism
createdb --owner=prism prism
make migrate
make dev
```

Open:

- Dashboard: <http://127.0.0.1:8000/dashboard/>
- OpenAPI: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

The core API and dashboard work without Microsoft or Azure credentials. Teams automation
remains unavailable until the Microsoft settings are configured.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

Compose starts PostgreSQL, applies Alembic migrations, and starts Prism on port `8000`.
The included password is for local development only. Replace it before using a persistent
or remotely reachable environment.

Stop the services with `docker compose down`. Add `--volumes` only when you intentionally
want to delete the local PostgreSQL data volume.

## Configuration

All configuration is read from environment variables or an ignored `.env` file. The
complete, commented list is in [.env.example](.env.example).

| Variable | Purpose | Default/safe state |
| --- | --- | --- |
| `APP_ENV` | Runtime environment; non-development modes require operator authentication | `development` |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL | Required |
| `MANAGER_TIMEZONE` | Interprets scheduled times and incomplete employee ETAs | `UTC` |
| `AGENT_SIGNATURE` | Signature appended to automated Teams messages | `Sent by Prism` |
| `OPERATOR_API_TOKEN` | Protects management APIs through `X-Manager-Operator-Token` | Required when public |
| `MICROSOFT_*` | Entra OAuth, token encryption, and webhook configuration | Disabled when blank |
| `INTELLIGENCE_LLM_ENABLED` | Enables Azure OpenAI-backed analysis | `false` in the example |
| `AZURE_OPENAI_*` | Azure OpenAI endpoint, key, API version, and deployments | Disabled when blank |
| `AUTOMATION_SCHEDULER_ENABLED` | Runs scheduled automation inside the API process | `false` |
| `DAILY_*_TIME` | Daily check-in, follow-up, and digest times | See `.env.example` |
| `MANAGER_NOTIFICATION_EMAIL` | Optional directory target for manager alerts | Blank |
| `MEMORY_*` | Organisational-memory limits and consolidation | Conservative defaults |

Generate local secret values without storing them in shell history manually:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit `.env`. Changing `MICROSOFT_TOKEN_ENCRYPTION_KEY` without reauthorizing the
Microsoft connection makes stored tokens unreadable.

## Microsoft Teams setup

Create a single-tenant Entra ID **Web** app registration with this local redirect URI:

```text
http://localhost:8000/api/v1/microsoft/auth/callback
```

Grant administrator consent for these delegated Microsoft Graph permissions:

```text
User.Read
User.Read.All
Chat.Create
Chat.Read
ChatMessage.Send
Mail.Send
```

Set the Microsoft variables in `.env`, expose port `8000` through a public HTTPS URL for
development, and set that origin as `MICROSOFT_WEBHOOK_BASE_URL`. Restart Prism after a
configuration change. For production, use a stable HTTPS deployment and a secret manager;
development tunnels are not a production deployment strategy.

Once connected from the dashboard:

1. Import the directory.
2. Mark only intended recipients as managed.
3. Start automation for the selected people.
4. Verify the first message and reply flow in a test account.

Every Graph notification is matched to an active subscription and validated with its
encrypted `clientState` before Prism fetches or stores the message.

## API and authentication

The main API groups are:

- `/api/v1`: employees, projects, tasks, daily updates, blockers, commitments,
  conversations, escalations, memory, Microsoft integration, and usage.
- `/api/v2/management`: aggregated management state, dependency graph, risks, decisions,
  attention, daily briefs, changes, feedback, and bounded queries.

When `APP_ENV` is not `development`, or a public webhook URL or operator token is set,
management APIs require this header:

```http
X-Manager-Operator-Token: <OPERATOR_API_TOKEN>
```

Health checks, Microsoft OAuth callbacks, and the Graph webhook remain public by design.
Domain errors use a stable JSON body with `detail` and `code` fields. Consult `/docs` for
the generated request and response schemas.

## Background jobs

The optional scheduler performs check-ins, follow-ups, listener renewal, daily briefs, and
memory consolidation. It is off by default. The scheduler runs inside the API process, so
enable it in only one process or replica; multiple scheduler-enabled workers can contend for
the same jobs even though outbound actions use idempotency keys.

## Testing and quality

```bash
make check          # lint, formatting check, type checking, unit tests, secret patterns
make test           # fast tests; PostgreSQL tests are skipped
make test-integration
make audit          # dependency vulnerability audit; requires network access
```

Integration tests use `DATABASE_URL` and can modify that database. Always point them at a
dedicated test database—never a development or production database.

Tests block live HTTP POST requests by default. Microsoft Graph and Azure OpenAI boundaries
must be mocked unless a deliberately isolated live acceptance test is being performed.

## Database migrations

```bash
make migrate
.venv/bin/alembic current
.venv/bin/alembic history
```

Create schema changes with Alembic and include both upgrade and downgrade behavior. Do not
edit an already published migration once external installations may have applied it.

## Project structure

```text
app/
  agents/       Structured AI decision prompts and orchestration
  api/routes/   FastAPI route groups
  core/         Configuration and request security
  db/           SQLAlchemy engine and sessions
  models/       PostgreSQL ORM models
  schemas/      API and decision validation models
  services/     Business logic and external integrations
  static/       Manager dashboard
alembic/        Database migration chain
scripts/        Repository maintenance checks
tests/          Unit and opt-in PostgreSQL integration tests
.github/        Contribution templates and CI/security automation
```

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Changes should remain
small, preserve the deterministic safety layer around AI decisions, and include regression
tests for message sending, authorization, data integrity, or migration behavior they affect.

## Security

Do not report vulnerabilities in a public issue. Follow [SECURITY.md](SECURITY.md) to open a
private GitHub security advisory. Prism handles employee messages and delegated Microsoft
tokens, so deployments should use isolated infrastructure, encrypted backups, HTTPS, a strong
operator token, and a managed secret store.

## Roadmap and support

See [ROADMAP.md](ROADMAP.md) for near-term priorities and [SUPPORT.md](SUPPORT.md) for support
boundaries. Changes are recorded in [CHANGELOG.md](CHANGELOG.md).

## Licence

No open-source licence has been selected yet. Until the copyright holder adds a licence,
the code is source-available for review but is **not** granted for use, modification, or
redistribution. Selecting and adding a licence is a blocker for the first public release.
