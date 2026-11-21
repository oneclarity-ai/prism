"""Shared skill definitions; private interviews and explicit, versioned Prism assignments."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PrismSkill(TimestampMixin, Base):
    __tablename__ = "prism_skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    # Onboarding-generated instructions stay private until explicitly copied to the library.
    owner_prism_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    required_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    required_connections: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PrismSkillAssignment(TimestampMixin, Base):
    __tablename__ = "prism_skill_assignments"

    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prism_skills.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Library edits never silently rewrite a Prism's approved instructions.
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PrismSkillSetup(TimestampMixin, Base):
    __tablename__ = "prism_skill_setups"

    prism_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prisms.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="questions")
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    suggestions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    generation_note: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=text("''")
    )
