# 05 — Data Model

Generic enough for future agents (Sales, Marketing); QA-specific data lives in `test_cases` and `bug_drafts`. All tables have `id` (UUID), `created_at`, `updated_at`. Add `org_id` now (single org in MVP) so multi-tenancy is a data change, not a rewrite.

## Tables

| Table | Key columns | Notes |
| --- | --- | --- |
| `users` | email, password_hash, role | Admin / member |
| `agents` | key, name, role, instructions, model, runtime (`openai_agents`), tool_grants (JSON), status (`active`/`paused`), monthly_budget_usd | One row = one agent "employee" |
| `target_apps` | name, base_url, environment, auth_secret_id, repo_url, notes | The app under test |
| `secrets` | name, encrypted_value, scope | Encrypt with a key from env (Fernet) for MVP; KMS later |
| `tasks` | title, goal, scope (JSON), target_app_id, agent_id, status (`todo`/`in_progress`/`blocked`/`done`/`failed`), schedule_cron, parent_id | `parent_id` keeps the goal → task tree idea from Paperclip |
| `runs` | task_id, agent_id, trigger (`manual`/`schedule`/`retry`), status (`queued`/`running`/`waiting_approval`/`succeeded`/`failed`/`cancelled`/`timed_out`), session_id, started_at, ended_at, input_tokens, output_tokens, cost_usd, error | One heartbeat = one run |
| `run_events` | run_id, seq, type (`message`/`tool_call`/`tool_result`/`status`/`log`), payload (JSON) | Live log; streamed to UI |
| `artifacts` | run_id, kind (`screenshot`/`report`/`test_script`/`trace`), path, mime, meta | Files stored outside the DB |
| `test_cases` | run_id, title, given, when, then, status (`pass`/`fail`/`blocked`/`skipped`), evidence_artifact_ids, notes | The test plan and results |
| `bug_drafts` | run_id, test_case_id, title, steps, expected, actual, severity, status (`draft`/`approved`/`filed`/`rejected`), external_url | Filed only after approval |
| `approvals` | run_id, action (`file_bug`, …), payload (JSON), status (`pending`/`approved`/`rejected`), decided_by, decided_at, comment | Ask-first gate |
| `budget_ledger` | agent_id, run_id, cost_usd, period (YYYY-MM) | Monthly spend per agent |

## Steps

1. Create SQLAlchemy models under `app/db/models/` (one file per table).
2. `alembic init alembic`, point it at the async engine, autogenerate the first migration, review it by hand.
3. Indexes: `runs(status, created_at)` for the queue, `run_events(run_id, seq)`, `tasks(agent_id, status)`.
4. Seed script `app/db/seed.py`: one admin user, the QA agent (instructions from `skills/qa/SKILL.md`), one target app pointing at the eval app.

## Done when

- `alembic upgrade head` creates all tables on a fresh DB.
- `uv run python -m app.db.seed` creates the admin, the QA agent and the eval-app target.
