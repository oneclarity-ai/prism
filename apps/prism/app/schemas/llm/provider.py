from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class ProviderStatusRead(Schema):
    provider: str
    model: str | None
    state: Literal["ready", "disabled", "not_configured", "invalid", "unavailable"]
    ready: bool
    detail: str
    credential_source: Literal["environment", "database", "local_login"]
    masked_key: str | None = None
    can_manage: bool


class OpenAICredentialUpsert(Schema):
    api_key: str = Field(min_length=20, max_length=512)
    model: str = Field(min_length=1, max_length=255)
