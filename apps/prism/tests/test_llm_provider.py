import json
import subprocess
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.services.errors import ExternalServiceError
from app.services.llm.llm_provider import (
    AnthropicProvider,
    AzureOpenAIProvider,
    CodexLocalProvider,
    CustomProvider,
    DeepSeekProvider,
    FakeLLMProvider,
    OpenAIProvider,
    ProviderResult,
    provider_from_settings,
    provider_status,
    validate_credential,
)

DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"


class ExampleOutput(BaseModel):
    answer: str


class OutputWithTitleField(BaseModel):
    title: str
    detail: str


def test_strict_schema_preserves_fields_named_like_schema_keywords() -> None:
    from app.services.llm.llm_service import strict_schema

    schema = strict_schema(OutputWithTitleField)

    assert set(schema["properties"]) == {"title", "detail"}
    assert schema["required"] == ["title", "detail"]
    assert "title" not in {key for key in schema if key != "properties"}


def test_provider_selection_and_safe_status() -> None:
    disabled = Settings(DATABASE_URL=DATABASE_URL, INTELLIGENCE_LLM_ENABLED=False)
    assert provider_status(disabled)["state"] == "disabled"

    azure = Settings(
        DATABASE_URL=DATABASE_URL,
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="azure_openai",
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
        AZURE_OPENAI_API_KEY="fake",
        AZURE_OPENAI_DEPLOYMENT="small",
    )
    assert isinstance(provider_from_settings(azure), AzureOpenAIProvider)
    assert provider_status(azure) == {
        "provider": "azure_openai",
        "model": "small",
        "state": "ready",
        "ready": True,
        "detail": "Ready",
    }

    openai = Settings(
        DATABASE_URL=DATABASE_URL,
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="openai",
        LLM_MODEL="test-model",
        OPENAI_API_KEY="secret",
    )
    assert isinstance(provider_from_settings(openai), OpenAIProvider)
    assert provider_status(openai)["ready"] is True


def test_fake_provider_is_deterministic() -> None:
    result = ProviderResult(text='{"answer":"done"}', model="fake-model")
    provider = FakeLLMProvider([result])

    returned = provider.generate_structured(
        prompt="prompt",
        context={"item": 1},
        output_model=ExampleOutput,
        model="fake-model",
        timeout_seconds=1,
    )

    assert returned == result
    assert provider.requests[0]["context"] == {"item": 1}


def test_codex_local_provider_uses_cli_auth_directory_without_reading_auth(
    monkeypatch, tmp_path
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth_path = codex_home / "auth.json"
    auth_path.write_text("contents-owned-by-codex", encoding="utf-8")
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        APP_ENV="development",
        LLM_PROVIDER="codex_local",
        LLM_MODEL="test-codex-model",
        CODEX_CLI_PATH="/usr/bin/true",
        CODEX_AUTH_PATH=str(auth_path),
    )
    provider = CodexLocalProvider(settings)
    captured = {}

    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"answer":"local"}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.llm.llm_provider.subprocess.run", run)
    result = provider.generate_structured(
        prompt="Return an answer",
        context={"item": 1},
        output_model=ExampleOutput,
        model="test-codex-model",
        timeout_seconds=5,
    )

    assert result.text == '{"answer":"local"}'
    assert captured["env"]["CODEX_HOME"] == str(codex_home)
    assert "contents-owned-by-codex" not in captured["input"]
    assert "--ephemeral" in captured["command"]
    assert ["--sandbox", "read-only"] == captured["command"][
        captured["command"].index("--sandbox") : captured["command"].index("--sandbox") + 2
    ]


def test_codex_local_provider_is_rejected_outside_development(tmp_path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("test", encoding="utf-8")
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        APP_ENV="production",
        INTELLIGENCE_LLM_ENABLED=True,
        LLM_PROVIDER="codex_local",
        CODEX_CLI_PATH="/usr/bin/true",
        CODEX_AUTH_PATH=str(auth_path),
    )

    assert provider_status(settings)["state"] == "invalid"


def test_codex_local_uses_longer_default_timeout_policy() -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        APP_ENV="development",
        LLM_PROVIDER="codex_local",
    )

    assert settings.selected_llm_timeout_seconds == 120
    assert settings.selected_llm_total_timeout_seconds == 180
    assert settings.selected_llm_max_attempts == 1


def test_codex_local_reports_timeout_precisely(monkeypatch, tmp_path) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text("owned-by-codex", encoding="utf-8")
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        APP_ENV="development",
        LLM_PROVIDER="codex_local",
        CODEX_CLI_PATH="/usr/bin/true",
        CODEX_AUTH_PATH=str(auth_path),
    )
    provider = CodexLocalProvider(settings)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("codex", 120)

    monkeypatch.setattr("app.services.llm.llm_provider.subprocess.run", timeout)

    with pytest.raises(ExternalServiceError, match="timed out after 120 seconds"):
        provider.generate_text(
            prompt="test",
            context={},
            model=provider.default_model(),
            timeout_seconds=120,
        )


def test_openai_adapter_uses_bearer_auth_and_structured_output(monkeypatch) -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="openai",
        LLM_MODEL="test-model",
        OPENAI_API_KEY="server-secret",
    )
    provider = OpenAIProvider(settings)
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={
                "id": "req_1",
                "model": "test-model",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                "choices": [{"message": {"content": json.dumps({"answer": "done"})}}],
            },
        )

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.post", post)
    result = provider.generate_structured(
        prompt="Return an answer",
        context={"item": 1},
        output_model=ExampleOutput,
        model="test-model",
        timeout_seconds=5,
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer server-secret"
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert result.text == '{"answer": "done"}'


def _azure(**extra) -> AzureOpenAIProvider:
    return AzureOpenAIProvider(
        Settings(
            DATABASE_URL=DATABASE_URL,
            INTELLIGENCE_LLM_ENABLED=True,
            LLM_PROVIDER="azure_openai",
            AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
            AZURE_OPENAI_API_KEY="fake",
            AZURE_OPENAI_DEPLOYMENT="gpt-5-nano",
            **extra,
        )
    )


def test_reasoning_models_are_asked_to_think_briefly_and_others_are_left_alone() -> None:
    assert _azure()._reasoning("gpt-5-nano") == {"reasoning_effort": "low"}
    assert _azure()._reasoning("o4-mini") == {"reasoning_effort": "low"}
    assert _azure()._reasoning("gpt-4o-mini") == {}
    assert _azure()._reasoning("gpt-5-chat") == {}  # chat variants do not reason
    assert _azure(AZURE_OPENAI_REASONING_EFFORT="")._reasoning("gpt-5-nano") == {}
    assert _azure(AZURE_OPENAI_REASONING_EFFORT="medium")._reasoning("gpt-5-nano") == {
        "reasoning_effort": "medium"
    }


def test_deepseek_adapter_uses_bearer_auth_against_its_own_base_url(monkeypatch) -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="deepseek",
        LLM_MODEL="deepseek-chat",
        DEEPSEEK_API_KEY="server-secret",
    )
    provider = DeepSeekProvider(settings)
    assert isinstance(provider_from_settings(settings), DeepSeekProvider)
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                "choices": [{"message": {"content": json.dumps({"answer": "done"})}}],
            },
        )

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.post", post)
    result = provider.generate_structured(
        prompt="Return an answer",
        context={"item": 1},
        output_model=ExampleOutput,
        model="deepseek-chat",
        timeout_seconds=5,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer server-secret"
    assert result.text == '{"answer": "done"}'


def test_custom_provider_requires_base_url_and_key() -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="custom",
        LLM_MODEL="some-model",
    )
    assert isinstance(provider_from_settings(settings), CustomProvider)
    assert CustomProvider(settings).is_configured() is False

    configured = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="custom",
        LLM_MODEL="some-model",
        CUSTOM_LLM_API_KEY="server-secret",
        CUSTOM_LLM_BASE_URL="https://example.internal/v1",
    )
    assert CustomProvider(configured).is_configured() is True


def test_anthropic_adapter_uses_tool_call_for_structured_output(monkeypatch) -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-sonnet-5-5",
        ANTHROPIC_API_KEY="server-secret",
    )
    provider = AnthropicProvider(settings)
    assert isinstance(provider_from_settings(settings), AnthropicProvider)
    captured = {}

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "model": "claude-sonnet-5-5",
                "usage": {"input_tokens": 3, "output_tokens": 2},
                "content": [
                    {"type": "tool_use", "name": "emit_result", "input": {"answer": "done"}}
                ],
            },
        )

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.post", post)
    result = provider.generate_structured(
        prompt="Return an answer",
        context={"item": 1},
        output_model=ExampleOutput,
        model="claude-sonnet-5-5",
        timeout_seconds=5,
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "server-secret"
    assert captured["json"]["system"] == "Return an answer"
    assert captured["json"]["tool_choice"] == {"type": "tool", "name": "emit_result"}
    assert json.loads(result.text) == {"answer": "done"}
    assert result.usage == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
        "prompt_tokens_details": {"cached_tokens": 0},
    }


def test_anthropic_adapter_reads_plain_text_block_for_text_generation(monkeypatch) -> None:
    settings = Settings(
        DATABASE_URL=DATABASE_URL,
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-sonnet-5-5",
        ANTHROPIC_API_KEY="server-secret",
    )
    provider = AnthropicProvider(settings)

    def post(_url, **_kwargs):
        return httpx.Response(
            200,
            json={"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "hello"}]},
        )

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.post", post)
    result = provider.generate_text(
        prompt="Say hello", context={}, model="claude-sonnet-5-5", timeout_seconds=5
    )

    assert result.text == "hello"


def test_credential_rejects_an_unauthorized_key_without_raising(monkeypatch) -> None:
    def get(_url, **_kwargs):
        return httpx.Response(401, json={})

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.get", get)
    ok, detail = validate_credential(
        provider_id="openai", api_key="sk-not-a-real-key-but-long-enough", model="gpt-4o-mini"
    )

    assert ok is False
    assert "rejected" in detail


def test_credential_accepts_a_working_key_and_checks_the_model_list(monkeypatch) -> None:
    def get(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer sk-real-enough-key-0000000000"
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.get", get)
    ok, detail = validate_credential(
        provider_id="openai",
        api_key="sk-real-enough-key-0000000000",
        model="gpt-4o-mini",
    )

    assert ok is True
    assert detail == "Key is valid"


def test_credential_requires_a_base_url_for_custom_providers() -> None:
    ok, detail = validate_credential(
        provider_id="custom", api_key="a-long-enough-fake-key-000000", model="anything"
    )

    assert ok is False
    assert "base URL" in detail


def test_credential_handles_transport_errors_without_raising(monkeypatch) -> None:
    def get(_url, **_kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.services.llm.llm_provider.httpx.get", get)
    ok, detail = validate_credential(
        provider_id="anthropic", api_key="a-long-enough-fake-key-000000", model="claude"
    )

    assert ok is False
    assert "reach" in detail
