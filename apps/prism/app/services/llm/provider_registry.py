"""Static catalog of LLM providers the dashboard can store a BYOK credential for.

This only describes what the Settings UI shows and what a credential needs; it is not
provider dispatch (see `llm_provider.provider_from_settings`) and it never holds a secret.
`codex_local` is deliberately excluded: it authenticates via a local CLI login, not an API key.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    label: str
    default_model_hint: str
    needs_base_url: bool = False
    base_url_required: bool = False
    needs_api_version: bool = False
    docs_url: str | None = None


PROVIDER_REGISTRY: list[ProviderDefinition] = [
    ProviderDefinition(
        id="openai",
        label="OpenAI",
        default_model_hint="gpt-4o-mini",
        docs_url="https://platform.openai.com/api-keys",
    ),
    ProviderDefinition(
        id="azure_openai",
        label="Azure OpenAI",
        default_model_hint="your deployment name",
        needs_base_url=True,
        base_url_required=True,
        needs_api_version=True,
        docs_url="https://portal.azure.com",
    ),
    ProviderDefinition(
        id="anthropic",
        label="Claude (Anthropic)",
        default_model_hint="claude-sonnet-5-5",
        docs_url="https://console.anthropic.com/settings/keys",
    ),
    ProviderDefinition(
        id="deepseek",
        label="DeepSeek",
        default_model_hint="deepseek-chat",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    ProviderDefinition(
        id="custom",
        label="Custom (OpenAI-compatible)",
        default_model_hint="model name",
        needs_base_url=True,
        base_url_required=True,
    ),
]

PROVIDER_BY_ID: dict[str, ProviderDefinition] = {
    definition.id: definition for definition in PROVIDER_REGISTRY
}
