"""One metered Azure structured-output boundary. No credential or prompt logging."""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Optional

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.llm_usage import LLMUsage
from app.services.errors import ExternalServiceError, RuleViolationError


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

    def normalize(node):
        if isinstance(node, dict):
            for keyword in unsupported:
                node.pop(keyword, None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class LLMService:
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
        deployment = deployment or settings.azure_openai_deployment
        if not (deployment and settings.azure_openai_endpoint and settings.azure_openai_api_key):
            raise RuleViolationError("Azure OpenAI endpoint, key and deployment must be configured")
        started = time.monotonic()
        payload = {}
        status = "failed"
        request_id = None
        try:
            last_error = None
            for attempt in range(settings.azure_openai_max_attempts):
                elapsed = time.monotonic() - started
                remaining = settings.azure_openai_total_timeout_seconds - elapsed
                if remaining <= 0:
                    break
                try:
                    response = httpx.post(
                        str(settings.azure_openai_endpoint).rstrip("/")
                        + "/openai/deployments/"
                        + deployment
                        + "/chat/completions",
                        params={"api-version": settings.azure_openai_api_version},
                        headers={"api-key": settings.azure_openai_api_key},
                        json={
                            "messages": [
                                {"role": "system", "content": prompt},
                                {"role": "user", "content": json.dumps(context, default=str)},
                            ],
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": output_model.__name__,
                                    "strict": True,
                                    "schema": strict_schema(output_model),
                                },
                            },
                        },
                        timeout=httpx.Timeout(
                            min(settings.azure_openai_timeout_seconds, remaining),
                            connect=min(10.0, max(1.0, remaining)),
                        ),
                    )
                    request_id = response.headers.get("apim-request-id") or response.headers.get(
                        "x-request-id"
                    )
                    payload = response.json()
                    if response.is_error:
                        if (
                            response.status_code not in {408, 409, 429}
                            and response.status_code < 500
                        ):
                            raise ExternalServiceError(
                                "Azure OpenAI request failed (HTTP {})".format(response.status_code)
                            )
                        raise httpx.HTTPStatusError(
                            "Transient Azure OpenAI response",
                            request=response.request,
                            response=response,
                        )
                    result = output_model.model_validate_json(
                        payload["choices"][0]["message"]["content"]
                    )
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
                    pause = 0.5 * (2**attempt)
                    if (
                        attempt + 1 < settings.azure_openai_max_attempts
                        and time.monotonic() - started + pause
                        < settings.azure_openai_total_timeout_seconds
                    ):
                        time.sleep(pause)
            raise ExternalServiceError(
                "Azure OpenAI did not return a valid response after {} attempts".format(
                    settings.azure_openai_max_attempts
                )
            ) from last_error
        finally:
            # Independent transaction retains actual billed usage even if validation
            # or a later management transaction fails. Unknown usage is not zero.
            payload = payload if isinstance(payload, dict) else {}
            usage = payload.get("usage") or {}
            model = str(payload.get("model") or deployment)
            pricing = settings.llm_model_pricing.get(model) or settings.llm_model_pricing.get(
                deployment
            )
            input_cost, output_cost, total_cost = calculate_cost(usage, pricing)
            with SessionLocal() as usage_db:
                usage_db.add(
                    LLMUsage(
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
                        request_id=request_id or payload.get("id"),
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=message_id,
                        latency_ms=round((time.monotonic() - started) * 1000),
                        status=status,
                    )
                )
                usage_db.commit()
