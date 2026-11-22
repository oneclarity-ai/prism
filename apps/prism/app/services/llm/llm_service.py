"""Metered provider-neutral generation facade. No credential or prompt logging."""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Optional

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.llm.llm_usage import LLMUsage
from app.services.errors import ExternalServiceError, RuleViolationError
from app.services.llm.llm_provider import LLMProvider, ProviderResult, provider_from_settings
from app.services.llm.provider_credential_service import ProviderCredentialService

logger = logging.getLogger(__name__)


def calculate_cost(usage: dict, pricing) -> tuple:
    """Cached tokens are part of input tokens, never an additional charge."""
    if pricing is None or "prompt_tokens" not in usage or "completion_tokens" not in usage:
        return None, None, None
    inputs = int(usage["prompt_tokens"])
    outputs = int(usage["completion_tokens"])
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
    if min(inputs, outputs, cached) < 0 or cached > inputs:
        return None, None, None
    million = Decimal(1_000_000)
    input_cost = (
        Decimal(inputs - cached) * Decimal(str(pricing.input))
        + Decimal(cached) * Decimal(str(pricing.cached_input))
    ) / million
    output_cost = Decimal(outputs) * Decimal(str(pricing.output)) / million
    return input_cost, output_cost, input_cost + output_cost


def strict_schema(model: type[BaseModel]) -> dict:
    """Return the JSON-Schema subset accepted by strict chat outputs.

    Pydantic still performs full validation after the provider responds, so
    application constraints remain enforced without sending Azure keywords it
    may reject.
    """

    schema = model.model_json_schema()
    unsupported = {
        "default",
        "title",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
    }

    def normalize(node, *, property_map: bool = False):
        if isinstance(node, dict):
            if not property_map:
                for keyword in unsupported:
                    node.pop(keyword, None)
            if not property_map and node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for key, value in node.items():
                normalize(value, property_map=key == "properties")
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class LLMService:
    provider_override: LLMProvider | None = None

    @classmethod
    def _provider(cls, settings) -> LLMProvider:
        return cls.provider_override or provider_from_settings(settings)

    @staticmethod
    def complete(
        *,
        prompt: str,
        context: dict,
        output_model: type[BaseModel],
        feature: str,
        deployment: Optional[str] = None,
        conversation_id=None,
        user_id=None,
        message_id=None,
    ):
        settings = get_settings()
        settings = ProviderCredentialService.effective_settings(settings)
        provider = LLMService._provider(settings)
        deployment = deployment or provider.default_model()
        if not deployment or not provider.is_configured():
            raise RuleViolationError("The selected LLM provider is not configured")
        started = time.monotonic()
        provider_result: ProviderResult | None = None
        status = "failed"
        try:
            last_error = None
            for attempt in range(settings.selected_llm_max_attempts):
                elapsed = time.monotonic() - started
                remaining = settings.selected_llm_total_timeout_seconds - elapsed
                if remaining <= 0:
                    break
                try:
                    provider_result = provider.generate_structured(
                        prompt=prompt,
                        context=context,
                        output_model=output_model,
                        model=deployment,
                        timeout_seconds=min(settings.selected_llm_timeout_seconds, remaining),
                    )
                    result = output_model.model_validate_json(provider_result.text)
                    status = "completed"
                    return result
                except (
                    httpx.TimeoutException,
                    httpx.TransportError,
                    httpx.HTTPStatusError,
                    ValueError,
                    KeyError,
                    IndexError,
                    TypeError,
                ) as exc:
                    last_error = exc
                    # Never log model text or prompts: only what kind of failure and where.
                    detail = (
                        [
                            (e["type"], ".".join(map(str, e["loc"])))
                            for e in exc.errors(include_input=False)[:5]
                        ]
                        if isinstance(exc, ValidationError)
                        else type(exc).__name__
                    )
                    logger.warning(
                        "llm_attempt_failed feature=%s attempt=%s detail=%s output_tokens=%s",
                        feature,
                        attempt + 1,
                        detail,
                        (provider_result.usage if provider_result else {}).get("completion_tokens"),
                    )
                    pause = 0.5 * (2**attempt)
                    if (
                        attempt + 1 < settings.selected_llm_max_attempts
                        and time.monotonic() - started + pause
                        < settings.selected_llm_total_timeout_seconds
                    ):
                        time.sleep(pause)
            if isinstance(last_error, httpx.TimeoutException):
                raise ExternalServiceError(
                    "The model provider timed out while preparing this review. Try again, or "
                    "increase the provider timeout for large Teams histories"
                ) from last_error
            if isinstance(last_error, httpx.TransportError):
                raise ExternalServiceError(
                    "The model provider could not be reached. Check the provider endpoint and "
                    "network connection"
                ) from last_error
            raise ExternalServiceError(
                "The model provider returned a response that Prism could not validate after {} "
                "attempts".format(settings.selected_llm_max_attempts)
            ) from last_error
        finally:
            # Independent transaction retains actual billed usage even if validation
            # or a later management transaction fails. Unknown usage is not zero.
            usage = provider_result.usage if provider_result else {}
            model = provider_result.model if provider_result else deployment
            pricing = settings.llm_model_pricing.get(model) or settings.llm_model_pricing.get(
                deployment
            )
            input_cost, output_cost, total_cost = calculate_cost(usage, pricing)
            with SessionLocal() as usage_db:
                usage_db.add(
                    LLMUsage(
                        provider=provider.name,
                        model=model,
                        deployment=deployment,
                        feature=feature,
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get(
                            "cached_tokens", 0
                        )
                        if usage
                        else None,
                        total_tokens=usage.get("total_tokens"),
                        estimated_input_cost_usd=input_cost,
                        estimated_output_cost_usd=output_cost,
                        estimated_total_cost_usd=total_cost,
                        pricing_snapshot=pricing.model_dump() if pricing else None,
                        request_id=provider_result.request_id if provider_result else None,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=message_id,
                        latency_ms=round((time.monotonic() - started) * 1000),
                        status=status,
                    )
                )
                usage_db.commit()
