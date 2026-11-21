from agents.models.chatcmpl_helpers import ChatCmplHelpers
from openai import AsyncAzureOpenAI

from app.core.config import get_settings
from app.runtime.openai_agents import _cost, model_settings


def test_cost_uses_per_deployment_rates_and_cached_tokens(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "azure_model_pricing",
        {"gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0}},
    )
    # 800k fresh + 200k cached input, 100k output
    assert _cost(1_000_000, 100_000, 200_000, "gpt-5-mini") == 0.2 + 0.005 + 0.2
    # unknown deployment falls back to the single prices
    fallback = settings.price_for("other")
    assert fallback == (
        settings.azure_price_input_per_1m,
        settings.cached_input_price,
        settings.azure_price_output_per_1m,
    )


def test_tiny_cost_is_not_rounded_away(monkeypatch):
    monkeypatch.setattr(get_settings(), "azure_model_pricing", {"m": {"input": 0.05, "output": 0.4}})
    assert 0 < _cost(120, 30, 0, "m") < 0.0001


def test_azure_stream_requests_provider_token_usage():
    client = AsyncAzureOpenAI(
        azure_endpoint="https://example.openai.azure.com/",
        api_key="unused-test-key",
        api_version="2025-04-01-preview",
    )
    try:
        assert ChatCmplHelpers.get_stream_options_param(client, model_settings("gpt-5-mini"), stream=True) == {
            "include_usage": True
        }
    finally:
        import asyncio

        asyncio.run(client.close())
