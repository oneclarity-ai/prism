from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.prisms.agent_sources import TeamsChatSourceRead, TeamsParticipantRead
from app.services.errors import RuleViolationError
from app.services.management.source_resolution_service import SourceResolutionService
from app.services.teams.teams_read_service import TeamsReadService


def source(
    external_id: str,
    label: str,
    chat_type: str,
    participants: list[tuple[str, str, list[str]]],
) -> TeamsChatSourceRead:
    return TeamsChatSourceRead(
        external_id=external_id,
        label=label,
        chat_type=chat_type,
        participants=[item[1] for item in participants],
        participant_details=[
            TeamsParticipantRead(external_id=item[0], display_name=item[1], aliases=item[2])
            for item in participants
        ],
        last_updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def catalog(monkeypatch):
    items = [
        source("private-parv", "Parv Pareek", "private", [("parv", "Parv Pareek", ["PP"])]),
        source(
            "release-group",
            "Release Group",
            "group",
            [("parv", "Parv Pareek", ["PP"]), ("meera", "Meera Shah", [])],
        ),
        source("ai-team", "AI Team", "group", [("atharv", "Atharv Rao", [])]),
    ]
    monkeypatch.setattr(TeamsReadService, "list_sources", lambda _db: items)
    return items


def test_person_name_prefers_private_chat(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "Check Parv's latest update")

    assert plan.status == "resolved"
    assert plan.selected.external_id == "private-parv"
    assert plan.selection_reason == "deterministic_alias"


def test_group_name_resolves_group_and_records_bounds(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "What is happening in the AI team?")

    assert plan.status == "resolved"
    assert plan.selected.external_id == "ai-team"
    assert plan.limits["sources"] == 5
    assert plan.limits["messages_per_source"] > 0


def test_attention_question_scans_all_recent_sources(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "What needs my attention across the team?")

    assert plan.status == "resolved"
    assert len(plan.selected_sources) == 3
    assert plan.selection_reason == "auto_all"
    assert plan.limits["history_days"] == 1


def test_explicit_all_available_sources_does_not_require_single_chat_choice() -> None:
    recent = datetime.now(timezone.utc)
    items = [
        source(
            f"chat-{index}",
            f"Team chat {index}",
            "group",
            [(f"person-{index}", f"Person {index}", [])],
        ).model_copy(update={"last_updated_at": recent})
        for index in range(8)
    ]

    plan = SourceResolutionService.resolve(
        None,
        (
            "Read my last 24 hours chats from all the available source, and let me know "
            "what needs my attention"
        ),
        catalog=items,
    )

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_all"
    assert len(plan.selected_sources) == 8
    assert plan.limits["sources"] == 50


def test_all_one_on_one_chats_and_24_hour_window_are_applied() -> None:
    recent = datetime.now(timezone.utc)
    items = [
        source("private-parv", "Parv Pareek", "private", [("parv", "Parv Pareek", [])]).model_copy(
            update={"last_updated_at": recent}
        ),
        source(
            "private-ajay", "Ajay Nikumbh", "private", [("ajay", "Ajay Nikumbh", [])]
        ).model_copy(update={"last_updated_at": recent}),
        source(
            "oneclarity-team",
            "OneClarity Team",
            "group",
            [("parv", "Parv Pareek", []), ("ajay", "Ajay Nikumbh", [])],
        ).model_copy(update={"last_updated_at": recent}),
        source(
            "private-old", "Old conversation", "private", [("old", "Old Person", [])]
        ).model_copy(update={"last_updated_at": recent - timedelta(days=2)}),
    ]

    plan = SourceResolutionService.resolve(
        None,
        "Read all my 1v1 chats with everyone from the last 24 hours",
        catalog=items,
    )

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_all"
    assert {item.external_id for item in plan.selected_sources} == {
        "private-parv",
        "private-ajay",
    }
    assert plan.limits["history_days"] == 1


def test_follow_up_question_scans_all_recent_private_and_group_chats() -> None:
    recent = datetime.now(timezone.utc)
    items = [
        source("private-ajay", "Ajay Nikumbh", "private", [("ajay", "Ajay", [])]),
        source(
            "oneclarity-team",
            "OneClarity Team",
            "group",
            [("ajay", "Ajay", []), ("parv", "Parv", [])],
        ),
        source("private-parv", "Parv Pareek", "private", [("parv", "Parv", [])]),
    ]
    items = [item.model_copy(update={"last_updated_at": recent}) for item in items]
    items.append(
        source("old-group", "Old Group", "group", [("old", "Old Person", [])]).model_copy(
            update={"last_updated_at": recent - timedelta(days=2)}
        )
    )

    plan = SourceResolutionService.resolve(
        None,
        "Do I need to followup with anyone?",
        catalog=items,
    )

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_all"
    assert {item.external_id for item in plan.selected_sources} == {
        "private-ajay",
        "oneclarity-team",
        "private-parv",
    }
    assert plan.limits["history_days"] == 1


def test_multiple_named_people_resolve_multiple_relevant_sources(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "Check Parv and Atharv's latest updates")

    assert plan.status == "resolved"
    assert {item.external_id for item in plan.selected_sources} == {
        "private-parv",
        "ai-team",
    }


def test_saved_person_alias_is_deterministic(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "Check PP's update")

    assert plan.status == "resolved"
    assert plan.selected.external_id == "private-parv"


def test_equal_private_name_matches_are_auto_included_without_picker(monkeypatch) -> None:
    items = [
        source("parv-1", "Parv Pareek", "private", [("parv-1", "Parv Pareek", [])]),
        source("parv-2", "Parv Sharma", "private", [("parv-2", "Parv Sharma", [])]),
    ]
    monkeypatch.setattr(TeamsReadService, "list_sources", lambda _db: items)

    plan = SourceResolutionService.resolve(None, "Check Parv's update")

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_ambiguous"
    assert {item.external_id for item in plan.selected_sources} == {"parv-1", "parv-2"}


def test_auto_falls_back_to_recent_sources_instead_of_requiring_picker(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "Help me prepare for tomorrow")

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_default"
    assert len(plan.selected_sources) == 3


def test_plural_one_on_one_draft_auto_selects_recent_private_chats() -> None:
    recent = datetime.now(timezone.utc)
    items = [
        source("private-ajay", "Ajay", "private", [("ajay", "Ajay", [])]),
        source("private-parv", "Parv", "private", [("parv", "Parv", [])]),
        source("group-team", "Team", "group", [("ajay", "Ajay", [])]),
    ]
    items = [item.model_copy(update={"last_updated_at": recent}) for item in items]

    plan = SourceResolutionService.resolve(
        None,
        "Draft a Teams message for 1:1 chats whose tasks are pending or were discussed",
        catalog=items,
    )

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_all"
    assert {item.external_id for item in plan.selected_sources} == {
        "private-ajay",
        "private-parv",
    }
    assert plan.limits["history_days"] == 1


def test_selected_chat_remains_a_hard_constraint_for_broad_prompt(catalog) -> None:
    plan = SourceResolutionService.resolve(
        None,
        "What needs my attention across all chats?",
        constrained_external_id="ai-team",
    )

    assert plan.status == "resolved"
    assert [item.external_id for item in plan.selected_sources] == ["ai-team"]
    assert plan.selection_reason == "explicit_constraint"


def test_explicit_exclusion_removes_matching_source(catalog) -> None:
    plan = SourceResolutionService.resolve(None, "Check Parv, but do not read the Release Group")

    assert plan.status == "resolved"
    assert plan.selected.external_id == "private-parv"
    assert plan.excluded_external_ids == ["release-group"]


def test_manager_choice_must_still_be_accessible(catalog) -> None:
    with pytest.raises(RuleViolationError, match="available to the connected manager"):
        SourceResolutionService.resolve(
            None,
            "Check Parv",
            selected_external_id="not-accessible",
        )


def test_manager_can_explicitly_select_multiple_private_and_group_chats(catalog) -> None:
    plan = SourceResolutionService.resolve(
        None,
        "Summarize the selected work.",
        selected_external_ids=["private-parv", "release-group", "private-parv"],
    )

    assert plan.status == "resolved"
    assert [item.external_id for item in plan.selected_sources] == [
        "private-parv",
        "release-group",
    ]
    assert plan.selection_reason == "manager_choice"


def test_prefiltered_prism_policy_catalog_cannot_be_bypassed_by_manual_selection(catalog) -> None:
    with pytest.raises(RuleViolationError, match="available to the connected manager"):
        SourceResolutionService.resolve(
            None,
            "Check the selected chat",
            selected_external_ids=["ai-team"],
            catalog=[catalog[0]],
        )


def _sweep_catalog():
    recent = datetime.now(timezone.utc)
    items = [
        source("dm-ajay", "Ajay Nikumbh", "private", [("ajay", "Ajay", [])]),
        source("dm-parv", "Parv Pareek", "private", [("parv", "Parv", [])]),
        source("dm-sanjay", "Sanjay Kumar", "private", [("sanjay", "Sanjay", [])]),
        source("team", "OneClarity Team", "group", [("ajay", "Ajay", []), ("parv", "Parv", [])]),
    ]
    items = [item.model_copy(update={"last_updated_at": recent}) for item in items]
    # Sanjay's own chat is quiet: no activity in the last 24 hours.
    items[2] = items[2].model_copy(update={"last_updated_at": recent - timedelta(days=3)})
    return items


GOAL = (
    "Read all my 1:1 chats from the last 24 hours, write a summary of what each person said, "
    "and send it to Sanjay"
)


def test_a_sweep_that_ends_with_send_it_to_a_person_reads_the_chats_not_just_that_person() -> None:
    plan = SourceResolutionService.resolve(None, GOAL, catalog=_sweep_catalog())

    assert plan.status == "resolved"
    assert plan.selection_reason == "auto_all"
    assert {item.external_id for item in plan.selected_sources} == {"dm-ajay", "dm-parv"}
    assert plan.limits["history_days"] == 1


def test_the_person_it_is_sent_to_is_the_destination_even_when_their_chat_was_quiet() -> None:
    catalog = _sweep_catalog()

    assert SourceResolutionService.destination_for(GOAL, catalog).external_id == "dm-sanjay"
    # Not a sweep: naming one person still means reading that person's chat.
    assert SourceResolutionService.destination_for("Check Parv's latest update", catalog) is None
    # No recipient at all.
    assert SourceResolutionService.destination_for("Read all my 1:1 chats today", catalog) is None


def test_two_equally_good_recipients_are_never_guessed() -> None:
    catalog = _sweep_catalog() + [
        source("dm-sanjay2", "Sanjay Rao", "private", [("sanjay2", "Sanjay", [])])
    ]

    assert SourceResolutionService.destination_for(GOAL, catalog) is None
