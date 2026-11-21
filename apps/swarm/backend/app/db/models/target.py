import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.db.enums import Environment


class Secret(IdMixin, TimestampMixin, Base):
    """Encrypted value. The API only ever returns names, never values."""

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_secrets_org_name"),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(64), default="general")
    encrypted_value: Mapped[str] = mapped_column(Text)


class TargetApp(IdMixin, TimestampMixin, Base):
    """A web app the QA agent tests."""

    __tablename__ = "target_apps"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(2000))
    environment: Mapped[str] = mapped_column(String(32), default=Environment.staging)
    auth_secret_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("secrets.id", ondelete="SET NULL"))
    repo_url: Mapped[str | None] = mapped_column(String(2000))
    notes: Mapped[str] = mapped_column(Text, default="")
    # Extra origins the agent's browser may load (CDN, SSO / login provider, API host).
    extra_origins: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")

    @property
    def has_test_login(self) -> bool:
        return self.auth_secret_id is not None
