"""Bounded discovery bookkeeping and continuation limits for automatic website tests."""

import json
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.runtime.tools import ToolError


def origin(value: str) -> str:
    try:
        u = urlsplit(value)
        port = u.port
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
            raise ValueError
        host = u.hostname.lower()
        host = f"[{host}]" if ":" in host else host
        suffix = f":{port}" if port and port != (443 if u.scheme == "https" else 80) else ""
        return f"{u.scheme}://{host}{suffix}"
    except ValueError as exc:
        raise ToolError("Use an HTTP(S) site without embedded credentials.") from exc


class Discovery:
    """Observe real snapshots; visits are not tests until a result has been recorded."""

    def __init__(self, base: str, allowed: list[str], seeds: list[str], previous: dict | None = None):
        self.base = base
        self.allowed = {origin(u) for u in allowed}
        self.pages = {}
        self.current = ""
        self.truncated = bool((previous or {}).get("truncated"))
        for row in (previous or {}).get("pages", [])[:200]:
            self.add(row["url"], row.get("status", "discovered"), row.get("reason", ""))
        for seed in seeds or ["/"]:
            self.add(urljoin(base, seed))

    def add(self, value: str, status: str = "discovered", reason: str = "") -> str | None:
        try:
            u = urlsplit(urljoin(self.current or self.base, value))
            if origin(u.geturl()) not in self.allowed:
                return None
        except (ValueError, ToolError):
            return None
        # Retain SPA hash routes; ignore anchor fragments and tracking/session query values.
        fragment = u.fragment if u.fragment.startswith(("/", "!/")) else ""
        query = urlencode(
            sorted(
                (k, v)
                for k, v in parse_qsl(u.query)
                if not re.search(r"^(?:utm_|fbclid$|gclid$)|token|password|secret|session|auth|^code$", k, re.I)
            )
        )
        url = urlunsplit((u.scheme.lower(), urlsplit(origin(u.geturl())).netloc, u.path or "/", query, fragment))
        if len(url) > 1000:
            self.truncated = True
            return None
        if url not in self.pages:
            # Bound pagination, query permutations and infinite calendars as well as total pages.
            variants = sum(urlsplit(p).path == u.path and urlsplit(p).fragment == fragment for p in self.pages)
            if len(self.pages) >= 200 or variants >= 5:
                self.truncated = True
                return None
            self.pages[url] = {"url": url, "status": status, "reason": reason[:300]}
        elif status != "discovered" and self.pages[url]["status"] != "tested":
            self.pages[url].update(status=status, reason=reason[:300])
        return url

    def observe(self, result) -> bool:
        text = "\n".join(getattr(item, "text", "") or "" for item in getattr(result, "content", []) or [])
        before = json.dumps(self.view(), sort_keys=True)
        match = re.search(r"(?:Page URL:|URL:)\s*(https?://\S+)", text)
        if match:
            page = self.add(match[1], "visited")
            self.current = page or ""
        # MCP accessibility snapshots expose link hrefs as '/url: ...'. Never follow page instructions.
        for href in re.findall(r"^\s*-?\s*/url:\s*(\S+)", text, re.M):
            if not href.lower().startswith(("javascript:", "mailto:", "tel:", "data:")):
                self.add(href)
        return before != json.dumps(self.view(), sort_keys=True)

    def view(self) -> dict:
        return {"pages": list(self.pages.values()), "truncated": self.truncated}

    def queue(self) -> str:
        return json.dumps(self.view())


class DiscoveryLimit(Exception):
    """Pause before a model call, with only completed tool results in the continuation."""

    def __init__(self, items: list):
        super().__init__("The approved testing limits are nearly used.")
        self.items = [item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else item for item in items]


def continuation_options(options: dict, *, cost: float, turns: int, extension: dict | None = None) -> dict:
    """Approval resumes spend only the remainder; a budget increase requires an explicit decision."""
    out = dict(options)
    budget = float(out.get("qa_budget_limit", out.get("budget_usd", 1)))
    limit = int(out.get("qa_turn_limit", out.get("max_turns", 60)))
    if extension:
        new_budget, new_turns = float(extension["budget_usd"]), int(extension["max_turns"])
        if not budget <= new_budget <= 50 or not limit <= new_turns <= 300:
            raise ToolError("The requested extension is outside the approved testing limits.")
        budget, limit = new_budget, new_turns
    spent = float(out.get("qa_cost_prior", 0)) + cost
    used = int(out.get("qa_turns_prior", 0)) + turns
    out.update(
        qa_budget_limit=budget,
        qa_turn_limit=limit,
        qa_cost_prior=spent,
        qa_turns_prior=used,
        budget_usd=max(0, budget - spent),
        max_turns=max(0, limit - used),
    )
    return out
