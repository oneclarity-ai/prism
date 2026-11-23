from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.schemas.prisms.agent_review import (
    ConversationReviewOutput,
    ReviewAttentionItem,
    ReviewProposedAction,
    ReviewProposedReply,
)
from app.services.errors import RuleViolationError
from app.services.management.conversation_review_service import (
    REVIEW_PROMPT,
    REVIEW_REPAIR_PROMPT,
    ConversationReviewService,
)


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
        "app.services.management.conversation_review_service.AgentPreferenceService.active",
        lambda db, thread_id: [SimpleNamespace(id=preference_id)],
    )

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return review(str(evidence_id))

    monkeypatch.setattr(
        "app.services.management.conversation_review_service.LLMService.complete", fake_complete
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
    assert captured["prompt"].startswith(REVIEW_REPAIR_PROMPT)
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


def test_attention_uncited_source_claim_is_replaced_by_cited_provenance() -> None:
    evidence_id = str(uuid.uuid4())
    output = review(evidence_id)
    output.attention_items[0].source_external_ids = ["chat-meera"]
    evidence = [SimpleNamespace(id=uuid.UUID(evidence_id), external_conversation_id="chat-parv")]

    annotated = ConversationReviewService._annotate_source_provenance(output, evidence)

    assert annotated.attention_items[0].source_external_ids == ["chat-parv"]


def test_evidence_ids_pasted_into_prose_are_removed_but_citations_stay() -> None:
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    output = review(first)
    output.summary = f"Fixes shipped last week. ({first}) Evidence: {second} and more."
    output.attention_items[0].detail = f"Needs a decision [evidence id: {first}, {second}] soon."
    evidence = [
        SimpleNamespace(id=uuid.UUID(first), external_conversation_id="chat-parv"),
        SimpleNamespace(id=uuid.UUID(second), external_conversation_id="chat-parv"),
    ]

    scrubbed = ConversationReviewService._scrub_evidence_ids(output, evidence)

    assert first not in scrubbed.summary and second not in scrubbed.summary
    assert scrubbed.summary.startswith("Fixes shipped last week.")
    assert first not in scrubbed.attention_items[0].detail
    assert scrubbed.attention_items[0].detail == "Needs a decision soon."
    assert scrubbed.attention_items[0].evidence_ids == output.attention_items[0].evidence_ids


def test_scrub_leaves_unrelated_uuids_and_text_alone() -> None:
    cited = str(uuid.uuid4())
    other = str(uuid.uuid4())
    output = review(cited)
    output.summary = f"Ticket {other} is still open."
    evidence = [SimpleNamespace(id=uuid.UUID(cited), external_conversation_id="chat-parv")]

    assert ConversationReviewService._scrub_evidence_ids(output, evidence).summary == output.summary


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

    from app.schemas.prisms.agent_review import ConversationReviewOutput
    from app.services.errors import RuleViolationError
    from app.services.management.conversation_review_service import ConversationReviewService

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


def test_every_drafting_prompt_carries_the_assistant_voice_and_no_manager_questions() -> None:
    from app.services.management import conversation_review_service as review

    voice = review.MESSAGE_VOICE
    flat = " ".join(voice.split())
    assert "write TO the recipient" in flat and "third person" in flat
    assert "real line breaks" in voice and "Yash here" in voice  # layout, and never as the manager
    # The old "write as the manager, first person" rule is gone from every prompt.
    for prompt in (
        review.REVIEW_PROMPT,
        review.INSTRUCTION_DRAFT_PROMPT,
        review.REVIEW_REPAIR_PROMPT,
    ):
        assert "write messages as them" not in prompt
        assert "first person" not in prompt


def test_a_cut_short_citation_is_dropped_when_real_ones_remain_and_resolved_when_unique() -> None:
    real, other = uuid.uuid4(), uuid.uuid4()
    evidence = [
        SimpleNamespace(id=real, external_message_id="m1", external_conversation_id="a"),
        SimpleNamespace(id=other, external_message_id="m2", external_conversation_id="b"),
    ]
    short = str(other)[:6] + "-..."  # a model shortening an id
    made_up = "0123abcd-ffff-4000-8000-000000000000"

    mixed_input = review(str(real)).model_copy(
        update={"summary_evidence_ids": [str(real), made_up]}
    )
    mixed = ConversationReviewService._normalize_citations(mixed_input, evidence)
    ConversationReviewService._validate_citations(mixed, evidence)  # no longer fails
    assert mixed.summary_evidence_ids == [str(real)]

    shortened = ConversationReviewService._normalize_citations(review(short), evidence)
    assert shortened.summary_evidence_ids == [str(other)]

    only_bogus = ConversationReviewService._normalize_citations(review(made_up), evidence)
    with pytest.raises(RuleViolationError, match="outside this job"):
        ConversationReviewService._validate_citations(only_bogus, evidence)


def test_tidy_message_drops_offers_the_recipients_own_line_repeats_and_sign_offs() -> None:
    from app.services.management.conversation_review_service import tidy_message

    body = (
        "Hi Sanjay, I'm Yash's chief of staff. He asked me to share an update.\n\n"
        "- Ajay: on track.\n"
        "- Sanjay Vitkare: nothing new.\n"
        "- Akshay: testing.\n"
        "- Akshay (follow-up): more testing.\n\n"
        "Please let Yash know if you'd like this reformatted.\n"
        "Warm regards\n"
        "— Yash's chief of staff"
    )

    assert tidy_message(body, "Sanjay") == (
        "Hi Sanjay, I'm Yash's chief of staff. He asked me to share an update.\n\n"
        "- Ajay: on track.\n"
        "- Akshay: testing."
    )


def test_the_prisms_own_instructions_reach_the_message_wording_step(monkeypatch) -> None:
    from app.schemas.prisms.agent_review import ReviewProposedReply
    from app.services.management import conversation_review_service as module

    seen: dict = {}

    def fake_complete(**kwargs):
        seen.update(kwargs["context"])
        return module._VoicedMessage(message="Hi Sanjay,\n\n- Ajay: on track.")

    monkeypatch.setattr(module.LLMService, "complete", staticmethod(fake_complete))
    monkeypatch.setattr(
        module.AgentPreferenceService,
        "active",
        staticmethod(
            lambda db, thread_id=None: [SimpleNamespace(instruction="Keep it under 5 lines")]
        ),
    )
    result = review(str(uuid.uuid4())).model_copy(
        update={
            "proposed_actions": [],
            "proposed_reply": ReviewProposedReply(body="draft", reason="r", evidence_ids=[]),
        }
    )
    context = {
        "prism_context": {"prism_name": "Chief of Staff"},
        "manager": {"first_name": "Yash"},
        "authorized_destinations": [
            {"external_id": "c1", "label": "Sanjay Vitkare", "chat_type": "private"}
        ],
        "evidence": [],
    }

    out = ConversationReviewService._apply_voice(
        None, SimpleNamespace(thread_id=uuid.uuid4()), context, result
    )

    assert seen["manager_instructions"] == ["Keep it under 5 lines"]
    assert out.proposed_reply.body.startswith("Hi Sanjay")
