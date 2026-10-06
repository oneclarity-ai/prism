# Contributing

Thank you for helping improve Prism. Contributions should be focused, testable, and safe for
a system that stores employee communication and can send messages through a manager account.

## Before you start

- Search existing issues and pull requests.
- Open a discussion or feature issue before a large architectural change.
- Report security vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
- Never include real employee messages, tenant identifiers, credentials, or customer data in
  issues, fixtures, screenshots, commits, or pull requests.

## Development setup

Requirements are Python 3.11+, PostgreSQL 14+, and Make.

```bash
git clone https://github.com/oneclarity-ai/prism.git
cd prism
cp .env.example .env
make setup
```

Create a dedicated local database, update `DATABASE_URL`, then run:

```bash
make migrate
make dev
```

The dashboard is available at <http://127.0.0.1:8000/dashboard/> and OpenAPI at
<http://127.0.0.1:8000/docs>.

## Development commands

```bash
make check              # all offline pull-request checks
make test               # unit tests; database tests skip
make test-integration   # requires a dedicated PostgreSQL DATABASE_URL
make lint
make format
make typecheck
make secrets
make audit              # vulnerability data requires network access
```

Type checking currently covers configuration/security, ORM models, and Pydantic schemas. This is
an intentional incremental boundary; expanding mypy coverage into services and route adapters is
tracked as maintenance work and should not be simulated with blanket ignores.

Do not point integration tests at any database containing useful data.

## Making changes

1. Create a short-lived branch from `main`.
2. Keep route handlers thin and put business rules in services.
3. Preserve the deterministic validation boundary around AI decisions.
4. Add or update tests for behavior changes and regressions.
5. Add an Alembic migration for schema changes; do not rely on ORM metadata creation.
6. Update documentation and `CHANGELOG.md` when user-visible behavior changes.
7. Run `make check` before opening the pull request.

Use clear, imperative commit subjects such as `Harden webhook validation`. Conventional Commits
are welcome but are not required. Avoid mixing unrelated refactors with behavior changes.

## Tests and external services

Automated tests must not call live Microsoft Graph or Azure OpenAI endpoints. Use explicit
fakes at the external boundary and synthetic `.example` or `.invalid` identities. A live
acceptance test belongs in an isolated tenant and must not be committed with its output.

For bug fixes, add a regression test that fails before the fix. Prioritize authorization,
automation recipient scope, message idempotency, webhook validation, data integrity, and
migration behavior over arbitrary coverage targets.

## Database migrations

```bash
.venv/bin/alembic revision --autogenerate -m "describe the schema change"
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade -1
```

Review generated migrations manually. Test both upgrade and downgrade against a disposable
database. Once a migration is included in a public release, add a new migration instead of
editing the published one.

## Pull requests

Pull requests should explain the problem, the chosen approach, test evidence, compatibility
impact, and any operational steps. Maintainers may ask for a smaller change when a review would
otherwise mix security-sensitive and cosmetic work.

At least one maintainer review is expected before merge. Security- or migration-sensitive
changes may require an additional reviewer. Prefer squash merging so `main` remains readable.

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
