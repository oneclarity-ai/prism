from functools import lru_cache
from pathlib import Path
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
    provider_credential_encryption_key: Optional[str] = Field(
        default=None, validation_alias="PROVIDER_CREDENTIAL_ENCRYPTION_KEY"
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
    prism_v21_enabled: bool = Field(default=False, validation_alias="PRISM_V21_ENABLED")
    prism_v22_enabled: bool = Field(default=False, validation_alias="PRISM_V22_ENABLED")
    prism_v22_single_executive_mode: bool = Field(
        default=False, validation_alias="PRISM_V22_SINGLE_EXECUTIVE_MODE"
    )
    v21_teams_message_limit: int = Field(
        default=50, ge=1, le=200, validation_alias="V21_TEAMS_MESSAGE_LIMIT"
    )
    v21_teams_source_limit: int = Field(
        default=5, ge=1, le=12, validation_alias="V21_TEAMS_SOURCE_LIMIT"
    )
    v21_teams_history_days: int = Field(
        default=30, ge=1, le=365, validation_alias="V21_TEAMS_HISTORY_DAYS"
    )
    v21_teams_evidence_character_limit: int = Field(
        default=60000,
        ge=5000,
        le=250000,
        validation_alias="V21_TEAMS_EVIDENCE_CHARACTER_LIMIT",
    )
    v22_teams_poll_source_limit: int = Field(
        default=8, ge=1, le=50, validation_alias="V22_TEAMS_POLL_SOURCE_LIMIT"
    )
    v22_teams_poll_message_limit: int = Field(
        default=100, ge=1, le=200, validation_alias="V22_TEAMS_POLL_MESSAGE_LIMIT"
    )
    v22_teams_event_limit: int = Field(
        default=100, ge=10, le=500, validation_alias="V22_TEAMS_EVENT_LIMIT"
    )
    v22_signal_model_enabled: bool = Field(
        default=False, validation_alias="V22_SIGNAL_MODEL_ENABLED"
    )
    v22_signal_unanswered_hours: int = Field(
        default=4, ge=1, le=168, validation_alias="V22_SIGNAL_UNANSWERED_HOURS"
    )
    v22_signal_lookback_hours: int = Field(
        default=168, ge=1, le=720, validation_alias="V22_SIGNAL_LOOKBACK_HOURS"
    )
    v22_signal_candidate_limit: int = Field(
        default=40, ge=1, le=100, validation_alias="V22_SIGNAL_CANDIDATE_LIMIT"
    )
    v22_presence_ttl_seconds: int = Field(
        default=120, ge=10, le=600, validation_alias="V22_PRESENCE_TTL_SECONDS"
    )
    v22_notification_expiry_minutes: int = Field(
        default=30, ge=1, le=1440, validation_alias="V22_NOTIFICATION_EXPIRY_MINUTES"
    )
    v22_incident_window_hours: int = Field(
        default=24, ge=1, le=168, validation_alias="V22_INCIDENT_WINDOW_HOURS"
    )
    v22_max_runs_per_day: int = Field(
        default=400, ge=1, le=5000, validation_alias="V22_MAX_RUNS_PER_DAY"
    )
    v22_max_model_calls_per_day: int = Field(
        default=100, ge=0, le=5000, validation_alias="V22_MAX_MODEL_CALLS_PER_DAY"
    )
    v22_max_consecutive_failures: int = Field(
        default=3, ge=1, le=20, validation_alias="V22_MAX_CONSECUTIVE_FAILURES"
    )
    v22_failure_backoff_minutes: int = Field(
        default=30, ge=1, le=1440, validation_alias="V22_FAILURE_BACKOFF_MINUTES"
    )
    v22_event_retention_days: int = Field(
        default=30, ge=8, le=365, validation_alias="V22_EVENT_RETENTION_DAYS"
    )
    prism_v22_scheduler_enabled: bool = Field(
        default=False, validation_alias="PRISM_V22_SCHEDULER_ENABLED"
    )
    prism_v22_scheduler_interval_seconds: int = Field(
        default=60, ge=15, le=3600, validation_alias="PRISM_V22_SCHEDULER_INTERVAL_SECONDS"
    )
    prism_v22_scheduler_global_concurrency: int = Field(
        default=1, ge=1, le=10, validation_alias="PRISM_V22_SCHEDULER_GLOBAL_CONCURRENCY"
    )
    prism_v22_scheduler_lease_seconds: int = Field(
        default=180, ge=30, le=1800, validation_alias="PRISM_V22_SCHEDULER_LEASE_SECONDS"
    )
    prism_v22_schedule_catch_up_seconds: int = Field(
        default=3600, ge=60, le=86400, validation_alias="PRISM_V22_SCHEDULE_CATCH_UP_SECONDS"
    )
    llm_provider: str = Field(default="azure_openai", validation_alias="LLM_PROVIDER")
    llm_model: Optional[str] = Field(default=None, validation_alias="LLM_MODEL")
    llm_reasoning_model: Optional[str] = Field(default=None, validation_alias="LLM_REASONING_MODEL")
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL"
    )
    codex_cli_path: str = Field(default="codex", validation_alias="CODEX_CLI_PATH")
    codex_auth_path: str = Field(
        default=str(Path.home() / ".codex" / "auth.json"),
        validation_alias="CODEX_AUTH_PATH",
    )
    codex_timeout_seconds: float = Field(
        default=120.0, ge=30.0, le=600.0, validation_alias="CODEX_TIMEOUT_SECONDS"
    )
    codex_total_timeout_seconds: float = Field(
        default=180.0, ge=60.0, le=900.0, validation_alias="CODEX_TOTAL_TIMEOUT_SECONDS"
    )
    codex_max_attempts: int = Field(default=1, ge=1, le=2, validation_alias="CODEX_MAX_ATTEMPTS")
    llm_timeout_seconds: Optional[float] = Field(
        default=None, ge=5.0, le=120.0, validation_alias="LLM_TIMEOUT_SECONDS"
    )
    llm_total_timeout_seconds: Optional[float] = Field(
        default=None, ge=10.0, le=180.0, validation_alias="LLM_TOTAL_TIMEOUT_SECONDS"
    )
    llm_max_attempts: Optional[int] = Field(
        default=None, ge=1, le=3, validation_alias="LLM_MAX_ATTEMPTS"
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

    @property
    def selected_llm_model(self) -> Optional[str]:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider.strip().casefold() == "azure_openai":
            return self.azure_openai_deployment
        return None

    @property
    def selected_reasoning_model(self) -> Optional[str]:
        if self.llm_reasoning_model:
            return self.llm_reasoning_model
        if self.llm_provider.strip().casefold() == "azure_openai":
            return self.azure_openai_reasoning_deployment
        return None

    @property
    def selected_llm_timeout_seconds(self) -> float:
        if (
            self.llm_provider.strip().casefold() == "codex_local"
            and self.llm_timeout_seconds is None
        ):
            return self.codex_timeout_seconds
        return self.llm_timeout_seconds or self.azure_openai_timeout_seconds

    @property
    def selected_llm_total_timeout_seconds(self) -> float:
        if (
            self.llm_provider.strip().casefold() == "codex_local"
            and self.llm_total_timeout_seconds is None
        ):
            return self.codex_total_timeout_seconds
        return self.llm_total_timeout_seconds or self.azure_openai_total_timeout_seconds

    @property
    def selected_llm_max_attempts(self) -> int:
        if self.llm_provider.strip().casefold() == "codex_local" and self.llm_max_attempts is None:
            return self.codex_max_attempts
        return self.llm_max_attempts or self.azure_openai_max_attempts

    @property
    def credential_encryption_key(self) -> Optional[str]:
        return self.provider_credential_encryption_key or self.microsoft_token_encryption_key


@lru_cache
def get_settings() -> Settings:
    # Pydantic supplies required fields from the environment at runtime; mypy
    # cannot infer BaseSettings aliases as constructor arguments.
    return Settings()  # type: ignore[call-arg]
