"""Provider-neutral model generation contracts and HTTP adapters."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.services.errors import ExternalServiceError, RuleViolationError


@dataclass(frozen=True)
class ProviderResult:
    text: str
    model: str
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def default_model(self) -> str | None: ...

    def generate_structured(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        output_model: type[BaseModel],
        model: str,
        timeout_seconds: float,
    ) -> ProviderResult: ...

    def generate_text(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        model: str,
        timeout_seconds: float,
    ) -> ProviderResult: ...


def _strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    # Imported lazily to avoid a module cycle with the compatibility facade.
    from app.services.llm.llm_service import strict_schema

    return strict_schema(model)


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(
            self.settings.azure_openai_endpoint
            and self.settings.azure_openai_api_key
            and self.default_model()
        )

    def default_model(self) -> str | None:
        return self.settings.llm_model or self.settings.azure_openai_deployment

    def _request(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        model: str,
        timeout_seconds: float,
        output_model: type[BaseModel] | None,
    ) -> ProviderResult:
        if not self.is_configured():
            raise RuleViolationError("Azure OpenAI endpoint, key and deployment must be configured")
        response_format: dict[str, Any] | None = None
        if output_model:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "strict": True,
                    "schema": _strict_schema(output_model),
                },
            }
        response = httpx.post(
            str(self.settings.azure_openai_endpoint).rstrip("/")
            + "/openai/deployments/"
            + model
            + "/chat/completions",
            params={"api-version": self.settings.azure_openai_api_version},
            headers={"api-key": self.settings.azure_openai_api_key},
            json={
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(context, default=str)},
                ],
                **({"response_format": response_format} if response_format else {}),
                **self._reasoning(model),
            },
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
        )
        return _chat_completion_result(response, fallback_model=model, provider_name=self.name)

    def _reasoning(self, deployment: str) -> dict[str, str]:
        effort = (self.settings.azure_openai_reasoning_effort or "").strip().lower()
        name = deployment.lower()
        if effort and name.startswith(("gpt-5", "o1", "o3", "o4")) and "chat" not in name:
            return {"reasoning_effort": effort}
        return {}

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._request(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._request(output_model=None, **kwargs)


def _openai_compatible_request(
    *,
    base_url: str,
    api_key: str,
    prompt: str,
    context: dict[str, Any],
    model: str,
    timeout_seconds: float,
    output_model: type[BaseModel] | None,
    provider_name: str,
) -> ProviderResult:
    """Shared /chat/completions call for OpenAI and any OpenAI-compatible endpoint."""

    response_format: dict[str, Any] | None = None
    if output_model:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "strict": True,
                "schema": _strict_schema(output_model),
            },
        }
    response = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(context, default=str)},
            ],
            **({"response_format": response_format} if response_format else {}),
        },
        timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
    )
    return _chat_completion_result(response, fallback_model=model, provider_name=provider_name)


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.openai_api_key and self.default_model())

    def default_model(self) -> str | None:
        return self.settings.llm_model

    def _request(self, **kwargs: Any) -> ProviderResult:
        if not self.is_configured():
            raise RuleViolationError("OpenAI API key and model must be configured")
        return _openai_compatible_request(
            base_url=self.settings.openai_base_url,
            api_key=str(self.settings.openai_api_key),
            provider_name=self.name,
            **kwargs,
        )

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._request(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._request(output_model=None, **kwargs)


class DeepSeekProvider:
    """DeepSeek's API is OpenAI-compatible; only the base URL and key differ."""

    name = "deepseek"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.deepseek_api_key and self.default_model())

    def default_model(self) -> str | None:
        return self.settings.llm_model

    def _request(self, **kwargs: Any) -> ProviderResult:
        if not self.is_configured():
            raise RuleViolationError("DeepSeek API key and model must be configured")
        return _openai_compatible_request(
            base_url=self.settings.deepseek_base_url,
            api_key=str(self.settings.deepseek_api_key),
            provider_name=self.name,
            **kwargs,
        )

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._request(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._request(output_model=None, **kwargs)


class CustomProvider:
    """A user-supplied OpenAI-compatible endpoint: self-hosted, a proxy, or any provider

    without a dedicated adapter.
    """

    name = "custom"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(
            self.settings.custom_llm_api_key
            and self.settings.custom_llm_base_url
            and self.default_model()
        )

    def default_model(self) -> str | None:
        return self.settings.llm_model

    def _request(self, **kwargs: Any) -> ProviderResult:
        if not self.is_configured():
            raise RuleViolationError(
                "Custom provider base URL, API key and model must be configured"
            )
        return _openai_compatible_request(
            base_url=str(self.settings.custom_llm_base_url),
            api_key=str(self.settings.custom_llm_api_key),
            provider_name=self.name,
            **kwargs,
        )

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._request(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._request(output_model=None, **kwargs)


_ANTHROPIC_MAX_TOKENS = 4096
_ANTHROPIC_TOOL_NAME = "emit_result"


class AnthropicProvider:
    """Claude's Messages API: a different shape (system is top-level, structured output

    goes through a forced tool call) normalized to the same ProviderResult contract.
    """

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.anthropic_api_key and self.default_model())

    def default_model(self) -> str | None:
        return self.settings.llm_model

    def _request(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        model: str,
        timeout_seconds: float,
        output_model: type[BaseModel] | None,
    ) -> ProviderResult:
        if not self.is_configured():
            raise RuleViolationError("Anthropic API key and model must be configured")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": _ANTHROPIC_MAX_TOKENS,
            "system": prompt,
            "messages": [{"role": "user", "content": json.dumps(context, default=str)}],
        }
        if output_model:
            body["tools"] = [
                {
                    "name": _ANTHROPIC_TOOL_NAME,
                    "description": "Return the result in the required structure.",
                    "input_schema": _strict_schema(output_model),
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": _ANTHROPIC_TOOL_NAME}
        response = httpx.post(
            self.settings.anthropic_base_url.rstrip("/") + "/v1/messages",
            headers={
                "x-api-key": str(self.settings.anthropic_api_key),
                "anthropic-version": self.settings.anthropic_api_version,
                "content-type": "application/json",
            },
            json=body,
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
        )
        return _anthropic_result(response, fallback_model=model, structured=bool(output_model))

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._request(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._request(output_model=None, **kwargs)


def _anthropic_result(
    response: httpx.Response, *, fallback_model: str, structured: bool
) -> ProviderResult:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalServiceError("anthropic returned an invalid response") from exc
    if response.is_error:
        if response.status_code not in {408, 409, 429} and response.status_code < 500:
            raise ExternalServiceError(f"anthropic request failed (HTTP {response.status_code})")
        raise httpx.HTTPStatusError(
            "Transient anthropic response", request=response.request, response=response
        )
    text: str | None = None
    for block in payload.get("content") or []:
        if structured and block.get("type") == "tool_use":
            text = json.dumps(block.get("input") or {})
            break
        if not structured and block.get("type") == "text":
            text = block.get("text")
            break
    if text is None:
        raise ExternalServiceError("anthropic returned no usable output")
    raw_usage = payload.get("usage") or {}
    usage: dict[str, Any] = {}
    if raw_usage:
        input_tokens = raw_usage.get("input_tokens") or 0
        output_tokens = raw_usage.get("output_tokens") or 0
        usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "prompt_tokens_details": {"cached_tokens": raw_usage.get("cache_read_input_tokens", 0)},
        }
    return ProviderResult(
        text=text,
        model=str(payload.get("model") or fallback_model),
        request_id=payload.get("id"),
        usage=usage,
    )


class FakeLLMProvider:
    """Deterministic provider for unit, contract, and end-to-end tests."""

    name = "fake"

    def __init__(self, results: list[ProviderResult] | None = None) -> None:
        self.results = list(results or [])
        self.requests: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    def default_model(self) -> str:
        return "fake-model"

    def _next(self, request: dict[str, Any]) -> ProviderResult:
        self.requests.append(request)
        if not self.results:
            raise ExternalServiceError("Fake provider has no queued result")
        return self.results.pop(0)

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._next(kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._next(kwargs)


class CodexLocalProvider:
    """Development-only adapter using the authenticated local Codex CLI."""

    name = "codex_local"
    DEFAULT_MODEL = "codex-config-default"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def auth_path(self) -> Path:
        return Path(self.settings.codex_auth_path).expanduser()

    def is_configured(self) -> bool:
        return bool(
            self.settings.app_env.casefold() == "development"
            and self.auth_path.is_file()
            and (
                Path(self.settings.codex_cli_path).is_file()
                or shutil.which(self.settings.codex_cli_path)
            )
        )

    def default_model(self) -> str:
        return self.settings.llm_model or self.DEFAULT_MODEL

    def _run(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        model: str,
        timeout_seconds: float,
        output_model: type[BaseModel] | None,
    ) -> ProviderResult:
        if self.settings.app_env.casefold() != "development":
            raise RuleViolationError("The local Codex provider is allowed only in development")
        if not self.is_configured():
            raise RuleViolationError("Codex CLI or its local authentication is unavailable")

        combined_prompt = "\n\n".join(
            [
                prompt,
                "Return only the requested final response. Do not inspect files or run tools.",
                "Input context:\n" + json.dumps(context, default=str),
            ]
        )
        with tempfile.TemporaryDirectory(prefix="prism-codex-") as directory:
            run_dir = Path(directory)
            answer_path = run_dir / "answer.txt"
            command = [
                self.settings.codex_cli_path,
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--cd",
                str(run_dir),
                "--output-last-message",
                str(answer_path),
            ]
            if model != self.DEFAULT_MODEL:
                command.extend(["--model", model])
            if output_model:
                schema_path = run_dir / "schema.json"
                schema_path.write_text(json.dumps(_strict_schema(output_model)), encoding="utf-8")
                command.extend(["--output-schema", str(schema_path)])
            command.append("-")
            child_env = os.environ.copy()
            child_env["CODEX_HOME"] = str(self.auth_path.parent)
            try:
                completed = subprocess.run(
                    command,
                    input=combined_prompt,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                    cwd=run_dir,
                    env=child_env,
                )
            except subprocess.TimeoutExpired as exc:
                raise ExternalServiceError(
                    f"The local Codex process timed out after {round(timeout_seconds)} seconds"
                ) from exc
            except OSError as exc:
                raise ExternalServiceError("The local Codex CLI could not be started") from exc
            if completed.returncode != 0 or not answer_path.is_file():
                raise ExternalServiceError("The local Codex process failed")
            return ProviderResult(text=answer_path.read_text(encoding="utf-8"), model=model)

    def generate_structured(self, **kwargs) -> ProviderResult:
        return self._run(**kwargs)

    def generate_text(self, **kwargs) -> ProviderResult:
        return self._run(output_model=None, **kwargs)


def _chat_completion_result(
    response: httpx.Response, *, fallback_model: str, provider_name: str
) -> ProviderResult:
    request_id = response.headers.get("apim-request-id") or response.headers.get("x-request-id")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalServiceError(f"{provider_name} returned an invalid response") from exc
    if response.is_error:
        if response.status_code not in {408, 409, 429} and response.status_code < 500:
            raise ExternalServiceError(
                f"{provider_name} request failed (HTTP {response.status_code})"
            )
        raise httpx.HTTPStatusError(
            f"Transient {provider_name} response", request=response.request, response=response
        )
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExternalServiceError(f"{provider_name} returned no model output") from exc
    return ProviderResult(
        text=text,
        model=str(payload.get("model") or fallback_model),
        request_id=request_id or payload.get("id"),
        usage=payload.get("usage") or {},
    )


def provider_from_settings(settings: Settings) -> LLMProvider:
    selected = settings.llm_provider.strip().casefold()
    if selected == "azure_openai":
        return AzureOpenAIProvider(settings)
    if selected == "openai":
        return OpenAIProvider(settings)
    if selected == "codex_local":
        return CodexLocalProvider(settings)
    if selected == "anthropic":
        return AnthropicProvider(settings)
    if selected == "deepseek":
        return DeepSeekProvider(settings)
    if selected == "custom":
        return CustomProvider(settings)
    raise RuleViolationError("Unsupported LLM provider: {}".format(settings.llm_provider))


def provider_status(settings: Settings) -> dict[str, str | bool | None]:
    selected = settings.llm_provider.strip().casefold()
    if selected == "azure_openai":
        selected_model = settings.llm_model or settings.azure_openai_deployment
    elif selected == "codex_local":
        selected_model = settings.llm_model or CodexLocalProvider.DEFAULT_MODEL
    else:
        selected_model = settings.llm_model
    if selected == "codex_local" and settings.app_env.casefold() != "development":
        return {
            "provider": selected,
            "model": selected_model,
            "state": "invalid",
            "ready": False,
            "detail": "Local Codex is restricted to development",
        }
    if not settings.intelligence_llm_enabled:
        return {
            "provider": selected,
            "model": selected_model,
            "state": "disabled",
            "ready": False,
            "detail": "Intelligence is disabled",
        }
    try:
        provider = provider_from_settings(settings)
    except RuleViolationError:
        return {
            "provider": selected,
            "model": None,
            "state": "invalid",
            "ready": False,
            "detail": "The selected provider is not supported",
        }
    ready = provider.is_configured()
    return {
        "provider": provider.name,
        "model": provider.default_model(),
        "state": "ready" if ready else "not_configured",
        "ready": ready,
        "detail": "Ready" if ready else "Required server configuration is missing",
    }


def _list_models_probe(
    url: str, *, headers: dict[str, str], label: str, model: str
) -> tuple[bool, str]:
    """A free "list models" call: confirms the key authenticates without spending tokens."""

    response = httpx.get(url, headers=headers, timeout=httpx.Timeout(10.0, connect=5.0))
    if response.status_code in {401, 403}:
        return False, "The API key was rejected"
    if response.is_error:
        return False, f"{label} returned HTTP {response.status_code}"
    if model:
        try:
            ids = {str(item.get("id")) for item in response.json().get("data", [])}
        except ValueError:
            ids = set()
        if ids and model not in ids:
            return True, f"Key is valid; model “{model}” was not in the account's list"
    return True, "Key is valid"


def validate_credential(
    *,
    provider_id: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
    api_version: str | None = None,
) -> tuple[bool, str]:
    """Validate a BYOK credential with a live, free call. Never raises; never logs the key."""

    selected = provider_id.strip().casefold()
    clean_key = (api_key or "").strip()
    clean_model = (model or "").strip()
    if len(clean_key) < 8:
        return False, "API key looks too short"
    try:
        if selected == "openai":
            return _list_models_probe(
                (base_url or "https://api.openai.com/v1").rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                label="OpenAI",
                model=clean_model,
            )
        if selected == "deepseek":
            return _list_models_probe(
                (base_url or "https://api.deepseek.com").rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                label="DeepSeek",
                model=clean_model,
            )
        if selected == "custom":
            if not base_url:
                return False, "A base URL is required for a custom provider"
            return _list_models_probe(
                base_url.rstrip("/") + "/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                label="The custom endpoint",
                model=clean_model,
            )
        if selected == "azure_openai":
            if not base_url:
                return False, "An endpoint is required for Azure OpenAI"
            response = httpx.get(
                base_url.rstrip("/") + "/openai/deployments",
                params={"api-version": api_version or "2024-10-21"},
                headers={"api-key": clean_key},
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            if response.status_code in {401, 403}:
                return False, "The API key was rejected"
            if response.is_error:
                return False, f"Azure OpenAI returned HTTP {response.status_code}"
            if clean_model:
                try:
                    names = {str(item.get("id")) for item in response.json().get("data", [])}
                except ValueError:
                    names = set()
                if names and clean_model not in names:
                    return (
                        True,
                        f"Key is valid; deployment “{clean_model}” was not found at this endpoint",
                    )
            return True, "Key is valid"
        if selected == "anthropic":
            response = httpx.get(
                (base_url or "https://api.anthropic.com").rstrip("/") + "/v1/models",
                headers={
                    "x-api-key": clean_key,
                    "anthropic-version": api_version or "2023-06-01",
                },
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            if response.status_code in {401, 403}:
                return False, "The API key was rejected"
            if response.is_error:
                return False, f"Anthropic returned HTTP {response.status_code}"
            return True, "Key is valid"
        return False, f"Unsupported provider: {provider_id}"
    except httpx.TimeoutException:
        return False, "The provider did not respond in time"
    except httpx.TransportError:
        return False, "Could not reach the provider endpoint"
