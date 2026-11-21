from __future__ import annotations

import pytest

from app.services.engine.work_plan_service import looks_like_task

BRIEF = (
    "# Task: Identify ideal customers for OneClarity\n"
    "Research companies that fit **OneClarity (https://oneclarity.ai/)**. It connects with "
    "workplace tools. Prefer organisations using Microsoft Teams, Slack, GitHub and Jira. "
    "Find at least 100 qualified companies and create a downloadable CSV."
)


def test_a_research_brief_that_names_teams_as_a_tool_is_a_web_task() -> None:
    assert looks_like_task(None, "Researcher", BRIEF) is True
    assert looks_like_task(None, "Researcher", "research companies using Slack and Teams") is True


@pytest.mark.parametrize(
    "text",
    [
        "read my teams chats and summarise",
        "check the Teams chat for blockers",
        "find what Sanjay said in the chat about pricing",
        "look up my chats with Ajay on teams",
    ],
)
def test_acting_on_teams_chats_is_not_a_web_task(text: str) -> None:
    assert looks_like_task(None, "Researcher", text) is False


def test_plain_replies_store_an_empty_metadata_dict_not_json_null() -> None:
    import inspect

    from app.services.qa.qa_run_service import QaRunService

    assert "message_metadata=extra or {}" in inspect.getsource(QaRunService._reply)
