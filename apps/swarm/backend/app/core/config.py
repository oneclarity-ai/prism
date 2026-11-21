from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OneClarity Agent Platform"
    environment: str = "local"
    log_level: str = "INFO"
    log_json: bool = True
    log_dir: Path | None = Path("./var/logs")  # set empty to disable file logs
    log_sql: bool = False  # true = log every SQL statement (very verbose)

    database_url: str = "postgresql+asyncpg://localhost:5432/oneclarity"

    # Auth
    jwt_secret: str = Field(default="change-me-in-env", min_length=16)
    jwt_algorithm: str = "HS256"
    session_ttl_minutes: int = 60 * 12
    session_cookie_name: str = "oc_session"
    cookie_secure: bool = False

    # Fernet key used to encrypt secrets at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]

    # Azure OpenAI (used by the agent runtime from milestone 3)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = ""
    azure_openai_deployment: str = ""
    # Price used to estimate cost (USD per 1M tokens). Set to your deployment's real rates.
    azure_price_input_per_1m: float = 2.50
    azure_price_output_per_1m: float = 10.00
    # Azure re-uses (caches) a repeated prompt start and bills it cheaper. Empty = 10% of the input price.
    azure_price_cached_input_per_1m: float | None = None
    # Per-deployment rates, JSON: {"gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0}}.
    # A deployment missing here falls back to the three single prices above.
    azure_model_pricing: dict[str, dict[str, float]] = {}
    # Cost controls for reasoning models (gpt-5*, o*): less hidden "thinking" = fewer output tokens.
    # Empty = the model's default (medium). Ignored for models without reasoning (gpt-4o*).
    azure_reasoning_effort: str = "low"
    azure_verbosity: str = "low"
    azure_max_retries: int = 6  # retries with backoff on HTTP 429 (rate limit) and 5xx
    # Context trimming: keep the last N tool outputs in full; older big ones are cut short.
    context_keep_recent_outputs: int = 4

    # Browser tool (Playwright MCP)
    playwright_mcp_package: str = "@playwright/mcp@0.0.83"
    browser_headless: bool = True

    # Computers: one Docker container (Playwright MCP + Chromium) per agent that has a "computer" grant.
    computers_dir: Path = Path("./var/computers")  # per-computer work folder, mounted at /work
    computer_image: str = "mcr.microsoft.com/playwright/mcp"  # pin a tag in .env for production
    computer_idle_minutes: int = 10  # a computer with no run for this long is stopped (its profile is kept)
    computer_memory: str = "1g"
    computer_cpus: str = "1"
    computer_start_timeout_sec: int = 60
    computer_frame_keep: int = 30  # live frames kept per run; report screenshots are never trimmed
    computer_allow_local_sites: bool = False  # explicit dev-only escape hatch for localhost/private targets
    # Words on a button or link that mean "this sends, posts, pays or deletes". Matching clicks wait for a human.
    outward_click_words: str = (
        "send,post,publish,submit,pay,buy,order,checkout,confirm,delete,remove,invite,connect,"
        "apply,book,subscribe,sign up,unsubscribe,place order,purchase,transfer"
    )

    # Prism bridge: Teams tools call back into Prism (signed with the shared secret).
    prism_bridge_url: str = ""
    prism_bridge_secret: str = ""

    # Runs
    artifacts_dir: Path = Path("./var/artifacts")
    run_timeout_sec: int = 1800
    max_concurrent_runs: int = 4  # runs (incl. sub-agents) at once; each opens a Chrome
    worker_poll_seconds: float = 1.0
    run_lease_seconds: int = 30
    approval_timeout_hours: int = 24
    # Parallel runs: defaults for each sub-agent (the Run dialog can change them per run).
    parallel_default_agents: int = 3
    parallel_max_children: int = 12
    subagent_max_turns: int = 80
    subagent_budget_usd: float = 1.0

    # Seed
    seed_admin_email: str = "admin@oneclarity.local"
    seed_admin_password: str = "change-me-now"

    def price_for(self, deployment: str | None) -> tuple[float, float, float]:
        """(input, cached input, output) USD per 1M tokens for a deployment."""
        row = self.azure_model_pricing.get(deployment or "") or {}
        inputs = float(row.get("input", self.azure_price_input_per_1m))
        cached = (
            float(row["cached_input"])
            if "cached_input" in row
            else (self.cached_input_price if "input" not in row else inputs * 0.1)
        )
        return inputs, cached, float(row.get("output", self.azure_price_output_per_1m))

    @property
    def cached_input_price(self) -> float:
        if self.azure_price_cached_input_per_1m is not None:
            return self.azure_price_cached_input_per_1m
        return self.azure_price_input_per_1m * 0.1

    @property
    def azure_configured(self) -> bool:
        return all(
            [
                self.azure_openai_endpoint,
                self.azure_openai_api_key,
                self.azure_openai_api_version,
                self.azure_openai_deployment,
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
