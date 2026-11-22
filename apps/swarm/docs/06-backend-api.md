# 06 — Backend API

All routes under `/api/v1`. Request and response bodies are Pydantic models in `app/schemas/`; the frontend types are generated from them (see 11).

## REST endpoints

| Area | Method + path | Purpose |
| --- | --- | --- |
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Session cookie |
| Agents | `GET /agents`, `POST /agents`, `GET /agents/{id}`, `PATCH /agents/{id}`, `POST /agents/{id}/pause`, `POST /agents/{id}/resume` | Manage agents |
| Target apps | `GET/POST /targets`, `GET/PATCH/DELETE /targets/{id}` | App under test |
| Secrets | `POST /secrets`, `GET /secrets` (names only), `DELETE /secrets/{id}` | Values are never returned |
| Tasks | `GET /tasks?status=&agent_id=`, `POST /tasks`, `GET /tasks/{id}`, `PATCH /tasks/{id}` | QA tasks |
| Runs | `POST /tasks/{id}/runs` (start), `GET /runs?task_id=`, `GET /runs/{id}`, `POST /runs/{id}/cancel` | Execution |
| Run detail | `GET /runs/{id}/events?after_seq=`, `GET /runs/{id}/test-cases`, `GET /runs/{id}/bugs`, `GET /runs/{id}/artifacts` | Report data |
| Artifacts | `GET /artifacts/{id}/file` | Streams the file (screenshot, report) |
| Approvals | `GET /approvals?status=pending`, `POST /approvals/{id}/decision` `{decision, comment}` | Ask-first inbox |
| Usage | `GET /usage?agent_id=&period=` | Tokens and cost |

## WebSocket

`GET /api/v1/ws` (authenticated). The client sends `{"subscribe": "run:<id>"}` or `{"subscribe": "approvals"}`. The server pushes:

```json
{ "topic": "run:<id>", "type": "run_event", "data": { "seq": 42, "type": "tool_call", "payload": { "tool": "browser_click", "args": { "element": "Sign in" } } } }
{ "topic": "run:<id>", "type": "run_status", "data": { "status": "waiting_approval" } }
{ "topic": "approvals", "type": "approval_created", "data": { "id": "…", "action": "file_bug" } }
```

Implementation: the worker writes `run_events` and calls `pg_notify('run_events', json)`; the API process `LISTEN`s and fans out to subscribed sockets. On reconnect the UI calls `GET /runs/{id}/events?after_seq=` to fill gaps.

## Steps

1. Pydantic schemas per resource (`Create`, `Update`, `Read`).
2. Service layer functions (no SQL in routers).
3. Routers with dependencies for session and current user.
4. WebSocket manager (topic → set of sockets) + Postgres listener task.
5. Pagination (`limit`, `cursor`) on list endpoints.
6. Pytest API tests with `httpx.AsyncClient` against a test DB.

## Done when

- Every endpoint above appears in `/docs` and has at least one test.
- A WebSocket client receives a fake event inserted by a test.
