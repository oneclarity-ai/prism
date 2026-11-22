from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

API = "/api/v1"


class SwarmError(Exception):
    """A failure talking to the testing workspace. The message is always safe to show."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class QaSwarmClient:
    """Server-side client for the hidden QA swarm. Its cookie, URL and ids never reach a browser."""

    def __init__(
        self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.qa_swarm_configured:
            raise SwarmError("My testing workspace isn't set up yet.")
        self._http = httpx.Client(
            base_url=self.settings.qa_swarm_url.rstrip("/"),
            timeout=httpx.Timeout(15.0, connect=5.0),
            transport=transport,
        )
        self._signed_in = False

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QaSwarmClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ---------- transport ----------

    def _login(self) -> None:
        try:
            response = self._http.post(
                f"{API}/auth/login",
                json={
                    "email": self.settings.qa_swarm_email,
                    "password": self.settings.qa_swarm_password,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("qa_swarm_unreachable", extra={"error": type(exc).__name__})
            raise SwarmError("My testing workspace is offline right now.") from exc
        if response.status_code >= 400:
            logger.warning("qa_swarm_login_failed", extra={"status": response.status_code})
            raise SwarmError("My testing workspace isn't accepting my sign-in.")
        self._signed_in = True

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._signed_in:
            self._login()
        for attempt in (0, 1):
            try:
                response = self._http.request(method, f"{API}{path}", **kwargs)
            except httpx.HTTPError as exc:
                logger.warning("qa_swarm_request_failed", extra={"error": type(exc).__name__})
                raise SwarmError("My testing workspace is offline right now.") from exc
            if response.status_code == 401 and attempt == 0:
                self._login()
                continue
            break
        if response.status_code >= 400:
            logger.warning(
                "qa_swarm_request_rejected",
                extra={
                    "path": re.sub(r"[0-9a-f-]{36}", "{id}", path),
                    "status": response.status_code,
                },
            )
            raise SwarmError("My testing workspace couldn't do that.", status=response.status_code)
        return response

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._request(method, path, **kwargs).json()

    # ---------- workspace ----------

    def status(self) -> dict:
        return self._json("GET", "/runtime/status")

    @staticmethod
    def _workspace_run(row: dict) -> dict:
        return {
            key: row.get(key)
            for key in (
                "id",
                "task_id",
                "agent_id",
                "task_title",
                "agent_name",
                "kind",
                "trigger",
                "runtime",
                "model",
                "status",
                "cancel_requested",
                "created_at",
                "started_at",
                "ended_at",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cost_usd",
                "total_cost_usd",
                "summary",
                "error",
                "active_tool",
            )
        }

    def workspace_data(
        self, section: str, *, days: int = 30, agent_id: str | None = None
    ) -> list[dict] | dict:
        """Read-only console data through an explicit allowlist; never proxy arbitrary paths."""
        paths = {
            "agents": ("/agents", {}),
            "tasks": ("/tasks", {"limit": 200}),
            "runs": ("/runs", {"limit": 200, "top_level": True}),
            "approvals": ("/approvals", {}),
            "bugs": ("/bugs", {"limit": 200}),
            "positions": ("/org/positions", {}),
            "targets": ("/targets", {}),
            "secrets": ("/secrets", {}),
            "usage": ("/usage", {}),
            "analytics": (
                "/analytics",
                {"days": days, **({"agent_id": agent_id} if agent_id else {})},
            ),
            "status": ("/runtime/status", {}),
        }
        if section not in paths:
            raise ValueError("Unknown workspace section")
        path, params = paths[section]
        result = self._json("GET", path, params=params)
        if section == "agents":
            return [
                {
                    **{
                        key: row.get(key)
                        for key in (
                            "id",
                            "key",
                            "name",
                            "role",
                            "description",
                            "runtime",
                            "model",
                            "status",
                            "reports_to_id",
                            "run_budget_usd",
                            "monthly_budget_usd",
                            "created_at",
                            "updated_at",
                        )
                    },
                    "tool_count": sum(
                        grant == "allowed" for grant in (row.get("tool_grants") or {}).values()
                    ),
                    "ask_first_count": sum(
                        grant == "ask_first" for grant in (row.get("tool_grants") or {}).values()
                    ),
                }
                for row in result
            ]
        if section == "runs":
            return [self._workspace_run(row) for row in result]
        if section == "approvals":
            safe_args = ("site", "summary", "question", "title", "reason")
            return [
                {
                    **{key: value for key, value in row.items() if key != "payload"},
                    "payload": {"arguments": {key: args[key] for key in safe_args if key in args}},
                }
                for row in result
                for payload in [row.get("payload")]
                for raw_args in [payload.get("arguments") if isinstance(payload, dict) else None]
                for args in [raw_args if isinstance(raw_args, dict) else {}]
            ]
        if section == "secrets":
            return [
                {key: row.get(key) for key in ("id", "name", "scope", "created_at")}
                for row in result
            ]
        return result

    def workspace_save(self, section: str, data: dict, record_id: str | None = None) -> dict:
        paths = {
            "tasks": "/tasks",
            "positions": "/org/positions",
            "targets": "/targets",
            "secrets": "/secrets",
        }
        if section not in paths or (section == "secrets" and record_id is not None):
            raise ValueError("Unsupported Workspace action")
        if record_id is not None:
            # IDs are validated again here for callers outside the HTTP adapter.
            from uuid import UUID

            path = f"{paths[section]}/{UUID(record_id)}"
        else:
            path = paths[section]
        result = self._json("PATCH" if record_id else "POST", path, json=data)
        if section == "secrets":
            return {key: result.get(key) for key in ("id", "name", "scope", "created_at")}
        return result

    def workspace_delete(self, section: str, record_id: str) -> None:
        from uuid import UUID

        paths = {"positions": "/org/positions", "targets": "/targets", "secrets": "/secrets"}
        if section not in paths:
            raise ValueError("Unsupported Workspace action")
        self._request("DELETE", f"{paths[section]}/{UUID(record_id)}")

    def workspace_run_detail(self, run_id: str) -> dict:
        """Gather the same run views used by the swarm console in one authenticated session."""
        return {
            "run": self._workspace_run(self.run(run_id)),
            "events": self.events(run_id, 0)[-200:],
            "subagents": self._json("GET", f"/runs/{run_id}/subagents"),
            "test_cases": self.test_cases(run_id),
            "bugs": self.bugs(run_id),
            "artifacts": [
                {key: row.get(key) for key in ("id", "kind", "mime", "created_at")}
                for row in self.artifacts(run_id)
            ],
        }

    def agent_id(self) -> str:
        wanted = self.settings.qa_swarm_agent.strip().lower()
        agents = self._json("GET", "/agents")
        for agent in agents:
            if str(agent.get("name", "")).strip().lower() == wanted:
                return agent["id"]
        raise SwarmError("My testing workspace doesn't have a tester set up yet.")

    def list_agents(self) -> list[dict]:
        return self._json("GET", "/agents")

    def find_agent(self, key: str) -> dict | None:
        return next((a for a in self._json("GET", "/agents") if a.get("key") == key), None)

    def create_agent(self, body: dict) -> dict:
        return self._json("POST", "/agents", json=body)

    def update_agent(self, agent_id: str, body: dict) -> dict:
        return self._json("PATCH", f"/agents/{agent_id}", json=body)

    # ---------- computers and saved logins ----------

    def computer(self, key: str) -> dict:
        return self._json("GET", f"/computers/{key}")

    def open_computer_stream(self, key: str) -> httpx.Response:
        """The live screen as an open streaming response (multipart JPEG). The caller closes it."""
        if not self._signed_in:
            self._login()
        request = self._http.build_request(
            "GET", f"{API}/computers/{key}/stream", timeout=httpx.Timeout(None, connect=5.0)
        )
        try:
            response = self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise SwarmError("My computer is offline right now.") from exc
        if response.status_code != 200:
            response.close()
            raise SwarmError("My computer isn't running.", status=response.status_code)
        return response

    def stop_computer(self, key: str) -> None:
        self._request("POST", f"/computers/{key}/stop")

    def reset_computer(self, key: str) -> None:
        self._request("POST", f"/computers/{key}/reset")

    def secrets(self, scope: str) -> list[dict]:
        return self._json("GET", "/secrets", params={"scope": scope})

    def create_secret(self, *, name: str, scope: str, value: str) -> str:
        return self._json("POST", "/secrets", json={"name": name, "scope": scope, "value": value})[
            "id"
        ]

    def delete_secret(self, secret_id: str) -> None:
        self._request("DELETE", f"/secrets/{secret_id}")

    # ---------- targets and tasks ----------

    def find_or_create_target(
        self, *, base_url: str, name: str, environment: str, notes: str, extra_origins: list[str]
    ) -> str:
        wanted = _origin(base_url)
        for target in self._json("GET", "/targets"):
            if _origin(str(target.get("base_url", ""))) == wanted:
                return target["id"]
        created = self._json(
            "POST",
            "/targets",
            json={
                "name": name[:200],
                "base_url": base_url,
                "environment": environment,
                "notes": notes,
                "extra_origins": extra_origins,
            },
        )
        return created["id"]

    def allow_target_origin(self, target_id: str, origin: str) -> None:
        """Add only the login site the manager approved to this test target's browser scope."""

        target = self._json("GET", f"/targets/{target_id}")
        base_origin = _origin(str(target["base_url"]))
        existing = list(target.get("extra_origins") or [])
        if origin != base_origin and origin not in existing and "*" not in existing:
            self._json(
                "PATCH",
                f"/targets/{target_id}",
                json={"extra_origins": [*existing, origin]},
            )

    def create_task(
        self,
        *,
        title: str,
        goal: str,
        agent_id: str,
        target_id: str | None,
        scope: dict,
        operation_key: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "title": title[:300],
            "goal": goal,
            "agent_id": agent_id,
            "scope": scope,
        }
        if operation_key:
            body["operation_key"] = operation_key
        if target_id:
            body["target_app_id"] = target_id
        return self._json("POST", "/tasks", json=body)["id"]

    def start_run(
        self,
        task_id: str,
        *,
        max_turns: int,
        budget_usd: float,
        pages: list[str],
        operation_key: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"mode": "single", "max_turns": max_turns, "budget_usd": budget_usd}
        if pages:
            body["pages"] = pages
        if operation_key:
            body["operation_key"] = operation_key
        return self._json("POST", f"/tasks/{task_id}/runs", json=body)

    # ---------- runs ----------

    def runs(self, *, since: str | None = None, limit: int = 200) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        return self._json("GET", "/runs", params=params)

    def run(self, run_id: str) -> dict:
        return self._json("GET", f"/runs/{run_id}")

    def events(self, run_id: str, after_seq: int) -> list[dict]:
        return self._json("GET", f"/runs/{run_id}/events", params={"after_seq": after_seq})

    def artifacts(self, run_id: str) -> list[dict]:
        return self._json("GET", f"/runs/{run_id}/artifacts")

    def artifact_file(self, artifact_id: str) -> tuple[bytes, str]:
        response = self._request("GET", f"/artifacts/{artifact_id}/file")
        return response.content, response.headers.get("content-type", "image/png")

    def test_cases(self, run_id: str) -> list[dict]:
        return self._json("GET", f"/runs/{run_id}/test-cases")

    def bugs(self, run_id: str) -> list[dict]:
        return self._json("GET", f"/runs/{run_id}/bugs")

    def cancel(self, run_id: str) -> dict:
        return self._json("POST", f"/runs/{run_id}/cancel")

    # ---------- approvals ----------

    def approvals(self) -> list[dict]:
        return self._json("GET", "/approvals")

    def decide(
        self,
        approval_id: str,
        decision: str,
        comment: str = "",
        payload: dict | None = None,
        operation_key: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"decision": decision, "comment": comment}
        if payload:
            body["payload"] = payload
        if operation_key:
            body["operation_key"] = operation_key
        return self._json("POST", f"/approvals/{approval_id}/decision", json=body)
