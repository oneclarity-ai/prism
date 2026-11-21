import pytest
from pydantic import ValidationError

from app.schemas.prisms.prism_skill import SkillApproval, SkillContent, SkillInterviewAnswer


def test_skill_contract_is_instruction_only_bounded_and_normalized():
    skill = SkillContent(
        name=" Lead research ",
        description=" Research prospects ",
        instructions=" Cite sources. ",
        required_tools=[" browser ", "browser"],
        required_connections=[" Outlook "],
    )
    assert skill.name == "Lead research"
    assert skill.required_tools == ["browser"]
    assert skill.required_connections == ["outlook"]
    with pytest.raises(ValidationError):
        SkillContent(**{**skill.model_dump(), "instructions": " "})
    with pytest.raises(ValidationError):
        SkillContent(**{**skill.model_dump(), "tool_grants": {"browser": "allowed"}})
    with pytest.raises(ValidationError):
        SkillApproval(expected_revision=1, skills=[skill] * 5)
    with pytest.raises(ValidationError):
        SkillInterviewAnswer(expected_revision=1, key="tasks", answer=" ")
