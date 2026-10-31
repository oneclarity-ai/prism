from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.schemas.agent_review import (
    ConversationReviewOutput,
    ReviewAttentionItem,
    ReviewProposedAction,
    ReviewProposedReply,
)
from app.services.conversation_review_service import (
    REVIEW_PROMPT,
    REVIEW_REPAIR_PROMPT,
    ConversationReviewService,
)
from app.services.errors import RuleViolationError


def review(evidence_id: str) -> ConversationReviewOutput:
    return ConversationReviewOutput(
        summary="A decision is needed.",
        summary_evidence_ids=[evidence_id],
        attention_items=[
            ReviewAttentionItem(
                title="Decision",
                detail="QA asked whether to proceed.",
                evidence_ids=[evidence_id],
            )
        ],
        manager_questions=[],
        requires_reply=True,
        proposed_reply=ReviewProposedReply(
            body="Please continue unaffected testing.",
            reason="Keep work moving.",
            evidence_ids=[evidence_id],
        ),
        confidence=0.8,
        limitations=[],
    )


def test_review_accepts_only_evidence_from_selected_job() -> None:
    evidence_id = str(uuid.uuid4())
    evidence = [SimpleNamespace(id=uuid.UUID(evidence_id))]

    ConversationReviewService._validate_citations(review(evidence_id), evidence)


def test_review_normalizes_external_message_ids_only_within_selected_job() -> None:
    selected_id = uuid.uuid4()
    evidence = [SimpleNamespace(id=selected_id, external_message_id="teams-message-42")]

    normalized = ConversationReviewService._normalize_citations(
        review("teams-message-42"), evidence
    )

    assert normalized.summary_evidence_ids == [str(selected_id)]
    assert normalized.attention_items[0].evidence_ids == [str(selected_id)]
    assert normalized.proposed_reply.evidence_ids == [str(selected_id)]


def test_review_normalizes_unique_short_uuid_prefix_only_within_selected_job() -> None:
    selected_id = uuid.UUID("414757d6-1111-4222-8333-123456789abc")
    other_id = uuid.UUID("73bb29e5-1111-4222-8333-123456789abc")
    evidence = [
        SimpleNamespace(id=selected_id, external_message_id="teams-message-1"),
        SimpleNamespace(id=other_id, external_message_id="teams-message-2"),
    ]

    normalized = ConversationReviewService._normalize_citations(
        review("Evidence ID: 414757d6"), evidence
    )

    assert normalized.summary_evidence_ids == [str(selected_id)]
    assert normalized.attention_items[0].evidence_ids == [str(selected_id)]
    assert normalized.proposed_reply.evidence_ids == [str(selected_id)]


def test_review_does_not_normalize_an_ambiguous_short_uuid_prefix() -> None:
    evidence = [
        SimpleNamespace(
            id=uuid.UUID("414757d6-1111-4222-8333-123456789abc"),
            external_message_id="teams-message-1",
        ),
        SimpleNamespace(
            id=uuid.UUID("414757d6-2222-4222-8333-123456789abc"),
            external_message_id="teams-message-2",
        ),
    ]

    normalized = ConversationReviewService._normalize_citations(review("414757d6"), evidence)

    with pytest.raises(RuleViolationError, match="outside this job's authorized Teams evidence"):
        ConversationReviewService._validate_citations(normalized, evidence)


def test_review_rejects_invented_citation() -> None:
    selected_id = uuid.uuid4()

    with pytest.raises(RuleViolationError, match="outside this job's authorized Teams evidence"):
        ConversationReviewService._validate_citations(
            review(str(uuid.uuid4())), [SimpleNamespace(id=selected_id)]
        )


def test_review_repair_receives_only_exact_authorized_boundary_values(monkeypatch) -> None:
    evidence_id = uuid.uuid4()
    preference_id = uuid.uuid4()
    invalid = review("not-an-authorized-evidence-id")
    captured = {}

    monkeypatch.setattr(
        "app.services.conversation_review_service.AgentPreferenceService.active",
        lambda db, thread_id: [SimpleNamespace(id=preference_id)],
    )

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return review(str(evidence_id))

    monkeypatch.setattr(
        "app.services.conversation_review_service.LLMService.complete", fake_complete
    )
    repaired = ConversationReviewService._repair_grounded_result(
        SimpleNamespace(),
        SimpleNamespace(thread_id=uuid.uuid4()),
        {"authorized_destinations": [{"external_id": "chat-sanjay"}]},
        invalid,
        [SimpleNamespace(id=evidence_id)],
        RuleViolationError("bad citation"),
    )

    assert repaired.summary_evidence_ids == [str(evidence_id)]
    assert captured["prompt"] == REVIEW_REPAIR_PROMPT
    assert captured["feature"] == "v21_conversation_review_repair"
    assert captured["context"]["allowed_evidence_ids"] == [str(evidence_id)]
    assert captured["context"]["allowed_destination_source_ids"] == ["chat-sanjay"]
    assert captured["context"]["allowed_preference_ids"] == [str(preference_id)]
    assert captured["context"]["validation_error"] == "bad citation"


def test_review_repair_prompt_forbids_message_ids_and_shortened_uuids() -> None:
    assert "Never cite a Teams message ID" in REVIEW_REPAIR_PROMPT
    assert "shortened UUID" in REVIEW_REPAIR_PROMPT


def test_inconsistent_model_action_shape_is_normalized_before_it_can_be_sent() -> None:
    evidence_id = str(uuid.uuid4())
    output = ConversationReviewOutput(
        summary="A decision is needed.",
        summary_evidence_ids=[evidence_id],
        attention_items=[],
        manager_questions=[],
        requires_reply=False,
        proposed_reply=ReviewProposedReply(
            body="Single reply", reason="One chat", evidence_ids=[evidence_id]
        ),
        proposed_actions=[
            ReviewProposedAction(
                destination_source_id="group-chat",
                body="Group reply",
                reason="Multiple sources",
                evidence_ids=[evidence_id],
                sequence=1,
            )
        ],
        confidence=0.5,
        limitations=[],
    )

    guarded = ConversationReviewService._enforce_action_intent(
        output, "Draft a message to the group.", source_count=2
    )

    assert guarded.requires_reply is True
    assert guarded.proposed_reply is None
    assert len(guarded.proposed_actions) == 1


def test_review_prompt_forbids_system_verification_as_an_insight() -> None:
    assert "Never describe source loading, read access" in REVIEW_PROMPT
    assert "actual work, commitments, unresolved decisions" in REVIEW_PROMPT


@pytest.mark.parametrize(
    "goal",
    [
        "What is going on with the team? Read all recent chats.",
        "Summarize the latest updates and blockers.",
        "Who still owes me an update?",
        "Do I need to reply to anything?",
    ],
)
def test_informational_goals_do_not_request_a_draft(goal: str) -> None:
    assert ConversationReviewService._explicit_draft_requested(goal) is False


@pytest.mark.parametrize(
    "goal",
    [
        "Draft a message asking the team for updates.",
        "What should I say in reply?",
        "Please follow up with the team about the release.",
        "Tell the team to post an ETA.",
        "Write a concise response to Sanjay.",
    ],
)
def test_explicit_action_goals_request_a_draft(goal: str) -> None:
    assert ConversationReviewService._explicit_draft_requested(goal) is True


def test_informational_goal_removes_model_generated_reply() -> None:
    evidence_id = str(uuid.uuid4())

    guarded = ConversationReviewService._enforce_action_intent(
        review(evidence_id), "What is going on with the team?"
    )

    assert guarded.requires_reply is False
    assert guarded.proposed_reply is None


def test_explicit_draft_goal_preserves_model_generated_reply() -> None:
    output = review(str(uuid.uuid4()))

    guarded = ConversationReviewService._enforce_action_intent(
        output, "Draft a reply asking QA to continue."
    )

    assert guarded.requires_reply is True
    assert guarded.proposed_reply == output.proposed_reply


def test_multisource_review_cannot_create_single_destination_draft() -> None:
    output = review(str(uuid.uuid4()))

    guarded = ConversationReviewService._enforce_action_intent(
        output,
        "Draft a follow-up to the team.",
        source_count=2,
    )

    assert guarded.requires_reply is False
    assert guarded.proposed_reply is None
    assert "name one destination" in guarded.limitations[0]


def test_attention_source_provenance_is_derived_from_citations() -> None:
    evidence_id = str(uuid.uuid4())
    output = review(evidence_id)
    evidence = [SimpleNamespace(id=uuid.UUID(evidence_id), external_conversation_id="chat-parv")]

    annotated = ConversationReviewService._annotate_source_provenance(output, evidence)

    assert annotated.attention_items[0].source_external_ids == ["chat-parv"]


def test_attention_cannot_claim_an_uncited_source() -> None:
    evidence_id = str(uuid.uuid4())
    output = review(evidence_id)
    output.attention_items[0].source_external_ids = ["chat-meera"]
    evidence = [SimpleNamespace(id=uuid.UUID(evidence_id), external_conversation_id="chat-parv")]

    with pytest.raises(RuleViolationError, match="source it did not cite"):
        ConversationReviewService._annotate_source_provenance(output, evidence)


def test_duplicate_external_message_id_is_not_an_ambiguous_citation_alias() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    evidence = [
        SimpleNamespace(id=first_id, external_message_id="duplicate", external_conversation_id="a"),
        SimpleNamespace(
            id=second_id, external_message_id="duplicate", external_conversation_id="b"
        ),
    ]

    normalized = ConversationReviewService._normalize_citations(review("duplicate"), evidence)

    with pytest.raises(RuleViolationError, match="outside this job"):
        ConversationReviewService._validate_citations(normalized, evidence)


def test_grounded_review_still_rejects_uncited_drafts_and_summaries() -> None:
    import pytest

    from app.schemas.agent_review import ConversationReviewOutput
    from app.services.conversation_review_service import ConversationReviewService
    from app.services.errors import RuleViolationError

    uncited_reply = ConversationReviewOutput(
        summary="Summary",
        summary_evidence_ids=["e1"],
        requires_reply=True,
        proposed_reply={"body": "Hi", "reason": "Because", "evidence_ids": []},
        confidence=0.9,
    )
    uncited_summary = ConversationReviewOutput(
        summary="Summary", summary_evidence_ids=[], requires_reply=False, confidence=0.9
    )
    for result in (uncited_reply, uncited_summary):
        with pytest.raises(RuleViolationError, match="without citing evidence"):
            ConversationReviewService._validate_citations(result, [])
