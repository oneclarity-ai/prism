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
    """Deprecated: kept for the legacy /api/v1/provider/openai routes. Prefer

    ProviderCredentialUpsert against /api/v1/provider/credentials/{provider_id}.
    """

    api_key: str = Field(min_length=8, max_length=512)
    model: str = Field(min_length=1, max_length=255)


class ProviderCredentialUpsert(Schema):
    api_key: str = Field(min_length=8, max_length=512)
    model: str = Field(min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=500)
    api_version: str | None = Field(default=None, max_length=40)


class ProviderCredentialSummary(Schema):
    provider: str
    label: str
    configured: bool
    is_active_provider: bool
    model: str | None = None
    masked_key: str | None = None
    base_url: str | None = None
    api_version: str | None = None
    needs_base_url: bool
    base_url_required: bool
    needs_api_version: bool
    default_model_hint: str
    docs_url: str | None = None
    can_manage: bool


class ProviderCredentialTestResult(Schema):
    ok: bool
    detail: str
