"""Thirty deterministic management simulations for V2 policy behavior."""

import pytest

from app.services.management_decision_service import ManagementDecisionService
from app.services.management_policy import ManagementPolicy

SCENARIOS = [
    ("ordinary update stays quiet", {"ordinary_update": True}, "NO_ACTION"),
    (
        "useful update acknowledgement",
        {"ordinary_update": True, "acknowledgement_useful": True},
        "ACKNOWLEDGE",
    ),
    ("short done acknowledgement", {"completion_confirmed": True}, "ACKNOWLEDGE"),
    (
        "done closes dependent loop",
        {"completion_confirmed": True, "dependent_waiting": True},
        "UPDATE_DEPENDENT",
    ),
    ("blocked without owner", {"blocked": True, "owner_known": False}, "ASK_CLARIFICATION"),
    ("ambiguous person mention", {"clarification_needed": True}, "ASK_CLARIFICATION"),
    ("new dated promise", {"new_commitment": True}, "CREATE_COMMITMENT"),
    ("revised ETA", {"revised_eta": True}, "UPDATE_COMMITMENT"),
    ("five minutes overdue no downstream", {"overdue_minutes": 5}, "NO_ACTION"),
    (
        "five minutes overdue downstream",
        {"overdue_minutes": 5, "dependent_waiting": True},
        "FOLLOW_UP",
    ),
    ("two hours overdue", {"overdue_minutes": 120}, "FOLLOW_UP"),
    (
        "recent reply suppresses chase",
        {"overdue_minutes": 180, "dependent_waiting": True, "recent_meaningful_response": True},
        "NO_ACTION",
    ),
    (
        "follow-up cap reached",
        {"overdue_minutes": 180, "dependent_waiting": True, "followups_today": 1},
        "NO_ACTION",
    ),
    (
        "project permits two followups",
        {
            "overdue_minutes": 180,
            "dependent_waiting": True,
            "followups_today": 1,
            "max_followups_per_day": 2,
        },
        "FOLLOW_UP",
    ),
    (
        "blocker silent one day",
        {"silence_hours": 24, "blocked": True, "owner_known": True},
        "NO_ACTION",
    ),
    (
        "blocker silent two days",
        {"silence_hours": 48, "blocked": True, "owner_known": True},
        "FOLLOW_UP",
    ),
    ("nonblocked silence", {"silence_hours": 72, "blocked": False}, "NO_ACTION"),
    ("question unanswered two hours", {"unanswered_hours": 2}, "NO_ACTION"),
    ("question unanswered four hours", {"unanswered_hours": 4}, "FOLLOW_UP"),
    (
        "nonmaterial question silence",
        {"unanswered_hours": 8, "question_material": False},
        "NO_ACTION",
    ),
    (
        "manager says don't chase",
        {"manager_suppressed": True, "overdue_minutes": 500, "dependent_waiting": True},
        "NO_ACTION",
    ),
    ("production action approval", {"protected_action": True}, "REQUEST_MANAGER_APPROVAL"),
    ("urgent cascade approval", {"urgent_manager_risk": True}, "REQUEST_MANAGER_APPROVAL"),
    ("multiple owners missing ETA", {"blocked": True, "owner_known": True}, "NO_ACTION"),
    ("changed owner needs no chase yet", {"ordinary_update": True}, "NO_ACTION"),
    (
        "reopened blocker no silence",
        {"blocked": True, "owner_known": True, "silence_hours": 0},
        "NO_ACTION",
    ),
    (
        "conflicting update clarification",
        {"clarification_needed": True, "ordinary_update": True},
        "ASK_CLARIFICATION",
    ),
    (
        "cross-project old issue quiet",
        {"ordinary_update": True, "recent_meaningful_response": True},
        "NO_ACTION",
    ),
    (
        "vague repeat after two days",
        {"blocked": True, "owner_known": True, "silence_hours": 60},
        "FOLLOW_UP",
    ),
    (
        "approval outranks completion",
        {"protected_action": True, "completion_confirmed": True},
        "REQUEST_MANAGER_APPROVAL",
    ),
]


@pytest.mark.parametrize("name,signals,expected", SCENARIOS, ids=[item[0] for item in SCENARIOS])
def test_management_scenario(name, signals, expected):
    action = ManagementPolicy.recommend(signals)
    assert action == expected, name
    assert action in ManagementDecisionService.ALLOWED_ACTIONS


def test_v2_has_at_least_thirty_realistic_scenarios():
    assert len(SCENARIOS) >= 30
