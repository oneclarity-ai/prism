"""Smoke test for the Azure OpenAI settings: `uv run python scripts/check_azure.py`.

Sends one short prompt through the OpenAI Agents SDK using the deployment in .env.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled  # noqa: E402
from openai import AsyncAzureOpenAI  # noqa: E402

from app.core.config import get_settings  # noqa: E402


async def main() -> int:
    s = get_settings()
    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_ENDPOINT": s.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": s.azure_openai_api_key,
            "AZURE_OPENAI_API_VERSION": s.azure_openai_api_version,
            "AZURE_OPENAI_DEPLOYMENT": s.azure_openai_deployment,
        }.items()
        if not value
    ]
    if missing:
        print(f"Missing in .env: {', '.join(missing)}")
        return 1

    set_tracing_disabled(True)  # keep traces out of the OpenAI platform
    client = AsyncAzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        api_version=s.azure_openai_api_version,
    )
    model = OpenAIChatCompletionsModel(model=s.azure_openai_deployment, openai_client=client)
    agent = Agent(name="Smoke test", instructions="Reply in five words or fewer.", model=model)
    result = await Runner.run(agent, "Say that the Azure connection works.")
    usage = result.context_wrapper.usage
    print(f"Reply: {result.final_output}")
    print(f"Tokens: input={usage.input_tokens} output={usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
