"""Explicit dashboard document paths; API and static-file 404s must stay 404s."""

import re

PAGES = {
    "chats",
    "spending",
    "workspace",
    "tasks",
    "runs",
    "approvals",
    "bugs",
    "prisms",
    "organization",
    "target-apps",
    "secrets",
    "run-analytics",
    "brain",
    "skills",
    "work",
    "approvals-inbox",
    "home",
    "assistant",
    "ask",
    "management",
    "journeys",
    "knowledge",
    "memory",
}
SETTINGS = {
    "account",
    "preferences",
    "notifications",
    "general",
    "teams",
    "archived",
    "connections",
    "provider",
    "access",
    "developer",
    "skills",
}
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
PRISM_KEY = rf"(?:p[A-Za-z0-9]{{5}}|[Pp][Rr]-[1-9][0-9]{{0,18}}|{UUID})"


def is_dashboard_path(path: str) -> bool:
    path = path.strip("/")
    if path in PAGES or path in {"", "settings"}:
        return True
    if path.startswith("settings/"):
        return path.split("/", 1)[1] in SETTINGS
    return bool(
        re.fullmatch(
            rf"prisms/{PRISM_KEY}(?:/settings(?:/(?:overview|instructions|skills|tools|tasks))?)?",
            path,
        )
        or re.fullmatch(rf"runs/{UUID}", path)
    )
