# Agent roles

One folder per role. The platform (runtime, tools, worker, API, UI) is shared; a role only adds
its identity, instructions and tool permissions.

| Folder | Agent | Department | Status |
| --- | --- | --- | --- |
| `qa/` | QA Agent | Technology | available |
| `sales/` | Sales SDR Agent | Sales | planned (needs CRM + email tools) |
| `marketing/` | Marketing Content Agent | Marketing | planned (needs CMS + social tools) |
| `support/` | Customer Support Agent | Customer Success | planned (needs helpdesk tools) |

## Add a new role

1. `mkdir app/agents/<role>` with `__init__.py`, `definition.py` (`DEFINITION = AgentDefinition(...)`) and `SKILL.md`.
2. Add it to `CATALOG` in `registry.py`.
3. If it needs new tools, add them to `app/runtime/tools.py` and wire them in `app/runtime/openai_agents.py`.
4. Set `status="available"` when ready; `python -m app.db.seed` then creates the agent row.
