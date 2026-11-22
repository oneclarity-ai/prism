from __future__ import annotations

from typing import Iterable

# What a Prism may use. Browsing is always on; the rest is chosen by the manager.
# "qa_kit" is not chosen by hand: the QA tester preset adds it.
CHOOSABLE = ("files", "teams")
ALL_CAPABILITIES = ("browser", "files", "teams", "qa_kit")

# Presets are data: a new role is an entry here, not a new code path.
PRESETS: dict[str, dict] = {
    "blank": {"label": "Custom role", "capabilities": ["browser"]},
    "executive_assistant": {"label": "Executive assistant", "capabilities": ["browser", "teams"]},
    "qa_tester": {"label": "QA tester", "capabilities": ["browser", "files", "qa_kit"]},
}

# Shown to the manager and enforced by the engine: these always wait for a yes.
ALWAYS_ASKS_FIRST = [
    "Signing in to a site",
    "Sending, posting or publishing anything",
    "Submitting a form with your details",
    "Buying, paying, ordering or deleting",
]


def normalize_capabilities(preset: str, chosen: Iterable[str] | None) -> list[str]:
    """Browser always; the preset's own capabilities; plus the manager's valid choices."""

    base = list(PRESETS.get(preset, PRESETS["blank"])["capabilities"])
    for value in chosen or []:
        if value in CHOOSABLE and value not in base:
            base.append(value)
    if "browser" not in base:
        base.insert(0, "browser")
    return base


def grants_for(capabilities: Iterable[str], logins_policy: str) -> dict[str, str]:
    """The engine's tool grants for a Prism. Anything not listed is off."""

    caps = set(capabilities)
    grants = {
        "get_task_context": "allowed",
        "add_note": "allowed",
        "update_checklist": "allowed",
        "complete_task": "allowed",
        "ask_manager": "ask_first",
        "confirm_action": "ask_first",
        "browser": "allowed",
        "computer": "allowed",
    }
    if "files" in caps:
        grants["save_file"] = "allowed"
    if "teams" in caps:
        grants.update(
            teams_search="allowed", teams_read_chat="allowed", teams_draft_message="allowed"
        )
    if logins_policy == "ask":
        grants.update(request_login="ask_first", sign_in="allowed")
    if "qa_kit" in caps:
        grants.update(
            save_test_plan="allowed",
            record_test_result="allowed",
            draft_bug="allowed",
            file_bug="ask_first",
        )
    return grants


def uses_labels(capabilities: Iterable[str]) -> list[str]:
    names = {
        "browser": "Browser",
        "files": "Files",
        "teams": "Teams",
        "qa_kit": "Test cases and bugs",
    }
    return [names[c] for c in ALL_CAPABILITIES if c in set(capabilities)]


# The Tools tab: every tool a Prism can be given, in the order shown. The grant for each is
# Allowed, Ask first or Off. Names match the engine's tool names; unknown names are harmless.
TOOL_CATALOG: list[dict[str, str]] = [
    {
        "name": "browser",
        "label": "Browser",
        "group": "Computer",
        "description": "Navigate, click, type and take screenshots in its own browser",
    },
    {
        "name": "computer",
        "label": "Computer",
        "group": "Computer",
        "description": "Use its own private computer for longer jobs",
    },
    {
        "name": "sign_in",
        "label": "Sign in to sites",
        "group": "Computer",
        "description": "Use logins you gave it, kept encrypted",
    },
    {
        "name": "request_login",
        "label": "Ask for a login",
        "group": "Computer",
        "description": "Ask you for a login when a site needs one",
    },
    {
        "name": "get_task_context",
        "label": "Read task context",
        "group": "Work",
        "description": "Goal, scope and target app of the task",
    },
    {
        "name": "get_test_login",
        "label": "Read test login",
        "group": "Work",
        "description": "Username and password for the target app",
    },
    {
        "name": "add_note",
        "label": "Add a note",
        "group": "Work",
        "description": "Progress notes on the task",
    },
    {
        "name": "update_checklist",
        "label": "Update checklist",
        "group": "Work",
        "description": "Tick off the steps of a task",
    },
    {
        "name": "complete_task",
        "label": "Complete task",
        "group": "Work",
        "description": "Final report and status",
    },
    {
        "name": "ask_manager",
        "label": "Ask you a question",
        "group": "Work",
        "description": "Pause and ask you when something is unclear",
    },
    {
        "name": "confirm_action",
        "label": "Confirm an action",
        "group": "Work",
        "description": "Wait for your yes before an outward action",
    },
    {
        "name": "save_file",
        "label": "Save files",
        "group": "Files",
        "description": "CSV, documents and screenshots it makes for you",
    },
    {
        "name": "teams_search",
        "label": "Search Teams",
        "group": "Teams",
        "description": "Search the chats you allow",
    },
    {
        "name": "teams_read_chat",
        "label": "Read Teams chats",
        "group": "Teams",
        "description": "Read chats you allow it to see",
    },
    {
        "name": "teams_draft_message",
        "label": "Draft Teams messages",
        "group": "Teams",
        "description": "Draft a message for your approval; it never sends on its own",
    },
    {
        "name": "save_test_plan",
        "label": "Save test plan",
        "group": "Testing",
        "description": "Write Given / When / Then cases",
    },
    {
        "name": "record_test_result",
        "label": "Record test result",
        "group": "Testing",
        "description": "Pass, fail or blocked with evidence",
    },
    {
        "name": "draft_bug",
        "label": "Draft bug",
        "group": "Testing",
        "description": "Prepare a bug report for review",
    },
    {
        "name": "file_bug",
        "label": "File bug externally",
        "group": "Testing",
        "description": "Create an issue in GitHub or Jira",
    },
]


def effective_grants(prism) -> dict[str, str]:
    """What the Prism's agent may do: the manager's own choices, else the role's defaults."""

    if prism.tool_grants:
        return dict(prism.tool_grants)
    return grants_for(prism.capabilities or ["browser"], prism.logins_policy)


def tools_for(prism) -> list[dict[str, str]]:
    grants = effective_grants(prism)
    known = {item["name"] for item in TOOL_CATALOG}
    rows = [{**item, "grant": grants.get(item["name"], "off")} for item in TOOL_CATALOG]
    for name, grant in sorted(grants.items()):
        if name not in known:
            rows.append(
                {
                    "name": name,
                    "label": name,
                    "group": "Other",
                    "description": "Custom tool",
                    "grant": grant,
                }
            )
    return rows
