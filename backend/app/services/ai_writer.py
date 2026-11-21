"""Small one-shot writing helpers on Azure OpenAI (not agent runs): e.g. an agent's job description."""

from typing import Any

from openai import AsyncAzureOpenAI

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import log

JOB_DESCRIPTION_PROMPT = """You write the job description for a new AI agent "employee" at OneClarity, a company
that runs a team of AI agents next to its people. Write it like a hiring manager hiring a real employee:
clear, specific, measurable. Use Markdown with exactly these sections:

## Mission
Two sentences: why this role exists and the value it delivers.

## Responsibilities
6-10 bullets, each starting with a verb.

## Day-to-day work
4-6 bullets describing a typical work session, step by step.

## Expected outcomes and KPIs
4-6 measurable outcomes (numbers, rates, time frames).

## Inputs, tools and access needed
What it needs to do the job (data, systems, accounts). Mark sensitive access as "needs approval".

## Boundaries
What it must never do on its own, and which actions need human approval.

## Reports to and works with
The manager role it reports to and the roles it hands work to or receives work from.

## Definition of done
How a finished piece of work looks.

Write for the role given. Do not invent company facts, customer names or numbers about the company;
KPI targets are suggestions the user can change. No preamble, start with "## Mission"."""


def _client() -> AsyncAzureOpenAI:
    s = get_settings()
    if not s.azure_configured:
        raise AppError(
            "Azure OpenAI is not configured, so AI writing is unavailable. Fill AZURE_OPENAI_* in backend/.env.",
            code="runtime_not_ready",
        )
    return AsyncAzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
        max_retries=s.azure_max_retries,
    )


async def complete(system: str, user: str, *, max_output_tokens: int = 4000) -> tuple[str, float]:
    """One chat completion. Returns (text, estimated cost in USD)."""
    from app.runtime.openai_agents import _cost, _is_reasoning_model  # SDK import only when used

    s = get_settings()
    deployment = s.azure_openai_deployment
    extra: dict[str, Any] = {"max_completion_tokens": max_output_tokens}
    if _is_reasoning_model(deployment):
        extra["reasoning_effort"] = s.azure_reasoning_effort or "low"
    r = await _client().chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **extra,
    )
    u = r.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    cost = _cost(u.prompt_tokens, u.completion_tokens, cached)
    return (r.choices[0].message.content or "").strip(), cost


async def job_description(name: str, role: str, department: str = "", notes: str = "") -> tuple[str, float]:
    facts = [f"Agent name: {name}", f"Role: {role}"]
    if department:
        facts.append(f"Department: {department}")
    if notes.strip():
        facts.append(f"Notes from the person hiring (use them): {notes.strip()}")
    text, cost = await _complete_or_fail(JOB_DESCRIPTION_PROMPT, "\n".join(facts))
    log.info("job_description_generated", agent=name, role=role, chars=len(text), cost_usd=round(cost, 5))
    return text, cost


async def _complete_or_fail(system: str, user: str) -> tuple[str, float]:
    try:
        text, cost = await complete(system, user)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - show a readable message in the UI
        log.warning("ai_writer_failed", error=str(exc)[:300])
        raise AppError(f"The AI writer failed: {exc}", code="ai_failed") from exc
    if not text:
        raise AppError("The AI writer returned an empty answer. Try again.", code="ai_failed")
    return text, cost
