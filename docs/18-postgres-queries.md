# 18 — Useful PostgreSQL Queries

Copy-paste queries for checking what the platform is doing. All of them were run against the `oneclarity` database on 2026-10-13. Tables for runs, events, approvals, test cases and bugs are empty until milestones 2–3, but the queries already work.

Table definitions: [05-data-model.md](05-data-model.md). Models in code: `backend/app/db/models/`.

## 18.1 Connect

```bash
psql oneclarity                 # dev database (local Homebrew Postgres)
psql oneclarity_test            # test database (recreated by pytest)
psql postgresql://oc:oc@localhost:5433/oneclarity   # if you use docker compose
```

Useful `psql` commands once connected:

| Command | What it does |
| --- | --- |
| `\dt` | List tables |
| `\d tasks` | Columns, indexes and foreign keys of a table |
| `\x auto` | Show wide rows vertically (good for JSON columns) |
| `\timing on` | Show how long each query takes |
| `\e` | Open the last query in your editor |
| `\q` | Quit |

## 18.2 Overview

Row count per table:

```sql
SELECT 'organizations' AS table_name, count(*) FROM organizations
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'agents', count(*) FROM agents
UNION ALL SELECT 'target_apps', count(*) FROM target_apps
UNION ALL SELECT 'secrets', count(*) FROM secrets
UNION ALL SELECT 'tasks', count(*) FROM tasks
UNION ALL SELECT 'runs', count(*) FROM runs
UNION ALL SELECT 'run_events', count(*) FROM run_events
UNION ALL SELECT 'approvals', count(*) FROM approvals;
```

Which migration the database is on (compare with `backend/alembic/versions/`):

```sql
SELECT version_num FROM alembic_version;
```

## 18.3 Agents

All agents with their settings:

```sql
SELECT key, name, role, status, runtime,
       COALESCE(NULLIF(model, ''), '(default)') AS model,
       max_turns, run_budget_usd, monthly_budget_usd
FROM agents
ORDER BY created_at;
```

Tool permissions, one row per tool (expands the `tool_grants` JSON):

```sql
SELECT a.key, g.tool, g.grant
FROM agents a, jsonb_each_text(a.tool_grants) AS g(tool, "grant")
ORDER BY a.key, g.tool;
```

Agents where filing bugs needs approval:

```sql
SELECT key, name FROM agents WHERE tool_grants ->> 'file_bug' = 'ask_first';
```

Set an agent back to the real runtime (same as the Runtime dropdown in the UI):

```sql
UPDATE agents SET runtime = 'openai_agents' WHERE key = 'qa-agent';
```

## 18.4 Tasks

Latest tasks with agent and target names:

```sql
SELECT t.title, t.status, a.name AS agent, ta.name AS target,
       t.scope ->> 'allow_bug_filing' AS bug_filing, t.created_at
FROM tasks t
JOIN agents a ON a.id = t.agent_id
LEFT JOIN target_apps ta ON ta.id = t.target_app_id
ORDER BY t.created_at DESC
LIMIT 20;
```

Tasks per status:

```sql
SELECT status, count(*) FROM tasks GROUP BY status ORDER BY count(*) DESC;
```

Every in-scope URL across tasks (expands the `scope.urls` JSON array):

```sql
SELECT t.title, u.url
FROM tasks t, jsonb_array_elements_text(t.scope -> 'urls') AS u(url);
```

## 18.5 Target apps and secrets

```sql
SELECT name, base_url, environment, auth_secret_id IS NOT NULL AS has_test_login, repo_url
FROM target_apps
ORDER BY name;
```

Secrets: list names only. `encrypted_value` is Fernet ciphertext and is useless without `SECRET_ENCRYPTION_KEY`; never copy it elsewhere.

```sql
SELECT name, scope, created_at FROM secrets ORDER BY name;
```

## 18.6 Runs (from milestone 2)

Latest runs with duration, tokens and cost:

```sql
SELECT r.id, t.title, r.status, r.trigger, r.started_at, r.ended_at,
       r.ended_at - r.started_at AS duration,
       r.input_tokens + r.output_tokens AS tokens, r.cost_usd, r.error
FROM runs r
JOIN tasks t ON t.id = r.task_id
ORDER BY r.created_at DESC
LIMIT 20;
```

Runs that look stuck (running for more than 30 minutes):

```sql
SELECT id, status, started_at
FROM runs
WHERE status = 'running' AND started_at < now() - interval '30 minutes';
```

Live log of one run (replace the id):

```sql
SELECT seq, type, payload ->> 'tool' AS tool, created_at
FROM run_events
WHERE run_id = '<run-id>'
ORDER BY seq;
```

### Parallel runs

A parallel run and its sub-agents (newest parallel run):

```sql
SELECT r.options->>'index' AS agent, r.options->>'label' AS pages, r.status,
       r.input_tokens + r.output_tokens AS tokens, r.cost_usd, r.started_at, r.ended_at, r.error
FROM runs r
WHERE r.parent_run_id = (SELECT id FROM runs WHERE kind = 'orchestrator' ORDER BY created_at DESC LIMIT 1)
ORDER BY (r.options->>'index')::int, r.created_at;
```

Total cost of each parallel run (merge + all sub-agents):

```sql
SELECT p.id, p.status, p.created_at,
       p.cost_usd + COALESCE(SUM(c.cost_usd), 0) AS total_cost_usd, COUNT(c.id) AS subagent_runs
FROM runs p LEFT JOIN runs c ON c.parent_run_id = p.id
WHERE p.kind = 'orchestrator'
GROUP BY p.id ORDER BY p.created_at DESC LIMIT 10;
```

Bugs marked as duplicates by a merge:

```sql
SELECT d.title AS duplicate, o.title AS same_as
FROM bug_drafts d JOIN bug_drafts o ON o.id = d.duplicate_of_id
ORDER BY d.created_at DESC;
```

## 18.7 QA results, bugs and approvals (from milestone 3)

Pass / fail / blocked per run:

```sql
SELECT r.id AS run_id,
       count(*) FILTER (WHERE tc.status = 'pass')    AS passed,
       count(*) FILTER (WHERE tc.status = 'fail')    AS failed,
       count(*) FILTER (WHERE tc.status = 'blocked') AS blocked
FROM runs r
LEFT JOIN test_cases tc ON tc.run_id = r.id
GROUP BY r.id;
```

Bug drafts, most severe first:

```sql
SELECT title, severity, status, external_url
FROM bug_drafts
ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END;
```

Approvals waiting for a human:

```sql
SELECT action, status, payload ->> 'title' AS title, created_at
FROM approvals
WHERE status = 'pending'
ORDER BY created_at;
```

## 18.8 Cost and budget

Spend per agent per month against its budget:

```sql
SELECT a.name, b.period, sum(b.cost_usd) AS spent, a.monthly_budget_usd,
       round(100 * sum(b.cost_usd) / NULLIF(a.monthly_budget_usd, 0), 1) AS pct_used
FROM budget_ledger b
JOIN agents a ON a.id = b.agent_id
GROUP BY a.name, b.period, a.monthly_budget_usd
ORDER BY b.period DESC, spent DESC;
```

## 18.9 Database health

Table sizes and row estimates:

```sql
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       n_live_tup AS rows_estimate
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

Open connections to the app database (the API keeps a small pool of idle ones; that is normal):

```sql
SELECT pid, usename, application_name, state, now() - query_start AS running_for, left(query, 80) AS query
FROM pg_stat_activity
WHERE datname = 'oneclarity';
```

## 18.10 Backup, restore and reset (shell commands)

```bash
pg_dump -Fc oneclarity > oneclarity_$(date +%Y%m%d).dump      # backup
pg_restore -d oneclarity --clean oneclarity_20261013.dump      # restore into existing DB
```

Reset the dev database to a clean, seeded state. **This deletes all data in `oneclarity`.**

```bash
dropdb oneclarity && createdb oneclarity
cd backend && uv run alembic upgrade head && uv run python -m app.db.seed
```

## Rules

- Change schema only through Alembic migrations (`uv run alembic revision --autogenerate -m "..."`), never with manual `ALTER TABLE` on shared databases.
- Prefer the API or UI for data changes; it validates input and keeps related rows (for example a target's login secret) consistent. Use `UPDATE` / `DELETE` in SQL only on your local dev database.
