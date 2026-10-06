from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPricing(BaseModel):
    input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    output: float = Field(ge=0)


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and `.env`."""

    app_name: str = Field(default="Prism", validation_alias="APP_NAME")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    database_url: str = Field(validation_alias="DATABASE_URL")
    microsoft_tenant_id: Optional[str] = Field(default=None, validation_alias="MICROSOFT_TENANT_ID")
    microsoft_client_id: Optional[str] = Field(default=None, validation_alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: Optional[str] = Field(
        default=None, validation_alias="MICROSOFT_CLIENT_SECRET"
    )
    microsoft_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/microsoft/auth/callback",
        validation_alias="MICROSOFT_REDIRECT_URI",
    )
    microsoft_webhook_base_url: Optional[str] = Field(
        default=None, validation_alias="MICROSOFT_WEBHOOK_BASE_URL"
    )
    microsoft_token_encryption_key: Optional[str] = Field(
        default=None, validation_alias="MICROSOFT_TOKEN_ENCRYPTION_KEY"
    )
    azure_openai_endpoint: Optional[str] = Field(
        default=None, validation_alias="AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_api_key: Optional[str] = Field(
        default=None, validation_alias="AZURE_OPENAI_API_KEY"
    )
    azure_openai_deployment: Optional[str] = Field(
        default=None, validation_alias="AZURE_OPENAI_DEPLOYMENT"
    )
    azure_openai_api_version: str = Field(
        default="2024-10-21", validation_alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_timeout_seconds: float = Field(
        default=25.0, ge=5.0, le=120.0, validation_alias="AZURE_OPENAI_TIMEOUT_SECONDS"
    )
    azure_openai_total_timeout_seconds: float = Field(
        default=40.0, ge=10.0, le=180.0, validation_alias="AZURE_OPENAI_TOTAL_TIMEOUT_SECONDS"
    )
    azure_openai_max_attempts: int = Field(
        default=2, ge=1, le=3, validation_alias="AZURE_OPENAI_MAX_ATTEMPTS"
    )
    azure_openai_reasoning_deployment: Optional[str] = Field(
        default=None, validation_alias="AZURE_OPENAI_REASONING_DEPLOYMENT"
    )
    response_policy_version: str = Field(
        default="2026-09-18.1", validation_alias="RESPONSE_POLICY_VERSION"
    )
    intelligence_llm_enabled: bool = Field(
        default=True, validation_alias="INTELLIGENCE_LLM_ENABLED"
    )
    llm_model_pricing: dict[str, ModelPricing] = Field(
        default_factory=dict, validation_alias="LLM_MODEL_PRICING"
    )
    agent_context_turns: int = Field(
        default=12, ge=2, le=30, validation_alias="AGENT_CONTEXT_TURNS"
    )
    agent_context_issues: int = Field(
        default=8, ge=1, le=20, validation_alias="AGENT_CONTEXT_ISSUES"
    )
    manager_timezone: str = Field(default="UTC", validation_alias="MANAGER_TIMEZONE")
    agent_signature: str = Field(
        default="Sent by Prism",
        min_length=1,
        max_length=120,
        validation_alias="AGENT_SIGNATURE",
    )
    automation_scheduler_enabled: bool = Field(
        default=False, validation_alias="AUTOMATION_SCHEDULER_ENABLED"
    )
    automation_scheduler_interval_seconds: int = Field(
        default=60, validation_alias="AUTOMATION_SCHEDULER_INTERVAL_SECONDS"
    )
    daily_checkin_time: str = Field(default="10:00", validation_alias="DAILY_CHECKIN_TIME")
    daily_followup_time: str = Field(default="13:00", validation_alias="DAILY_FOLLOWUP_TIME")
    daily_digest_time: str = Field(default="19:30", validation_alias="DAILY_DIGEST_TIME")
    digest_due_soon_hours: int = Field(default=48, validation_alias="DIGEST_DUE_SOON_HOURS")
    manager_notification_email: Optional[str] = Field(
        default=None, validation_alias="MANAGER_NOTIFICATION_EMAIL"
    )
    operator_api_token: Optional[str] = Field(default=None, validation_alias="OPERATOR_API_TOKEN")
    management_context_max_entries: int = Field(
        default=60, validation_alias="MANAGEMENT_CONTEXT_MAX_ENTRIES"
    )
    management_response_context_max_entries: int = Field(
        default=8,
        ge=1,
        le=20,
        validation_alias="MANAGEMENT_RESPONSE_CONTEXT_MAX_ENTRIES",
    )
    memory_engine_enabled: bool = Field(default=True, validation_alias="MEMORY_ENGINE_ENABLED")
    memory_embeddings_enabled: bool = Field(
        default=False, validation_alias="MEMORY_EMBEDDINGS_ENABLED"
    )
    azure_openai_embedding_deployment: Optional[str] = Field(
        default=None, validation_alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    )
    memory_context_max_facts: int = Field(default=8, validation_alias="MEMORY_CONTEXT_MAX_FACTS")
    memory_context_max_episodes: int = Field(
        default=4, validation_alias="MEMORY_CONTEXT_MAX_EPISODES"
    )
    memory_context_max_relations: int = Field(
        default=6, validation_alias="MEMORY_CONTEXT_MAX_RELATIONS"
    )
    memory_context_max_evidence: int = Field(
        default=5, validation_alias="MEMORY_CONTEXT_MAX_EVIDENCE"
    )
    memory_consolidation_enabled: bool = Field(
        default=True, validation_alias="MEMORY_CONSOLIDATION_ENABLED"
    )
    memory_consolidation_time: str = Field(
        default="02:00", validation_alias="MEMORY_CONSOLIDATION_TIME"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # Pydantic supplies required fields from the environment at runtime; mypy
    # cannot infer BaseSettings aliases as constructor arguments.
    return Settings()  # type: ignore[call-arg]
