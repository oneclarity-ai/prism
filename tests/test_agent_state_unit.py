import itertools

from app.models.enums import AgentJobState, AgentStepState
from app.services.agent_state_service import (
    JOB_TRANSITIONS,
    STEP_TRANSITIONS,
    canonical_payload_hash,
)


def test_every_job_state_pair_is_explicitly_allowed_or_forbidden() -> None:
    assert set(JOB_TRANSITIONS) == set(AgentJobState)
    for source, target in itertools.product(AgentJobState, repeat=2):
        allowed = target in JOB_TRANSITIONS[source]
        if source in {AgentJobState.COMPLETED, AgentJobState.FAILED, AgentJobState.CANCELLED}:
            assert allowed is False
        if source == target:
            assert allowed is False


def test_every_step_state_pair_is_explicitly_allowed_or_forbidden() -> None:
    assert set(STEP_TRANSITIONS) == set(AgentStepState)
    for source, target in itertools.product(AgentStepState, repeat=2):
        if source in {AgentStepState.COMPLETED, AgentStepState.FAILED, AgentStepState.CANCELLED}:
            assert target not in STEP_TRANSITIONS[source]


def test_payload_hash_is_canonical_and_binds_destination_and_body() -> None:
    first = canonical_payload_hash(
        action="teams.send_chat_message",
        destination={"chat_id": "chat-1", "recipients": ["person-1"]},
        body="Approved text",
    )
    reordered = canonical_payload_hash(
        action="teams.send_chat_message",
        destination={"recipients": ["person-1"], "chat_id": "chat-1"},
        body="Approved text",
    )
    changed = canonical_payload_hash(
        action="teams.send_chat_message",
        destination={"chat_id": "chat-1", "recipients": ["person-1"]},
        body="Changed text",
    )

    assert first == reordered
    assert first.startswith("sha256:") and len(first) == 71
    assert changed != first
