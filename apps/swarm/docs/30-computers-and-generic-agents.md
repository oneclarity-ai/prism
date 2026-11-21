# 30 — Computers and generic agents (Prism v2.4)

An agent whose `tool_grants` include `computer` gets its own **computer**: a Docker container
(`prism-computer-<agent key>`) running the Playwright MCP server and Chromium, with a named volume
`prism-profile-<key>` for its browser profile and `var/computers/<key>/work` mounted at `/work`.

- `app/computers/manager.py` creates, wakes, stops and resets computers through the `docker` CLI. The allowed
  origins of a task are passed as `--allowed-origins`; a changed list recreates the container (profile kept).
- `app/runtime/computer_mcp.py` wraps the MCP browser: clicks whose label sounds outward wait for approval,
  results are masked, and a live frame is taken after each acting step (`artifact` event, kind `frame`).
- Tools follow the agent's grants: `add_note`, `update_checklist`, `ask_manager`, `confirm_action`, `request_login`,
  `sign_in`, `save_file`, `teams_*` (calls back into Prism, HMAC signed), plus the QA kit when granted.
- Approvals take an optional `payload` on decision (`{"answer": "..."}`); the resumed run hands it to the tool.
- `runs.result` holds what `complete_task` returned (results rows and files).
- One run at a time per computer. The worker's reaper stops idle computers.
- API: `GET /computers/{key}`, `POST /computers/{key}/stop|reset`, `GET /secrets?scope=`.
