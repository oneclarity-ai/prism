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
            get_test_login="allowed",
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
