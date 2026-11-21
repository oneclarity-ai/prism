from agents.run import CallModelData, ModelInputData

from app.core.config import get_settings
from app.runtime.openai_agents import _cost, _trim_old_outputs, model_settings


def test_old_big_outputs_are_trimmed_recent_kept():
    big = "x" * 5000
    items = [{"role": "user", "content": "start"}]
    for i in range(10):
        items.append({"type": "function_call", "call_id": f"c{i}", "name": "browser_snapshot", "arguments": "{}"})
        items.append({"type": "function_call_output", "call_id": f"c{i}", "output": big})
    data = CallModelData(model_data=ModelInputData(input=items, instructions="x"), agent=None, context=None)

    keep = get_settings().context_keep_recent_outputs
    out = _trim_old_outputs(data).input
    outputs = [i["output"] for i in out if i.get("type") == "function_call_output"]
    assert all(len(o) < 600 and "trimmed" in o for o in outputs[:-keep])
    assert all(o == big for o in outputs[-keep:])
    assert items[2]["output"] == big, "original list must not be modified"
    assert len(out) == len(items)


def test_cached_tokens_are_cheaper(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "azure_price_input_per_1m", 0.25)
    monkeypatch.setattr(s, "azure_price_output_per_1m", 2.0)
    monkeypatch.setattr(s, "azure_price_cached_input_per_1m", None)
    full = _cost(1_000_000, 0)
    assert round(full, 4) == 0.25
    assert round(_cost(1_000_000, 0, cached_tokens=1_000_000), 4) == 0.025


def test_reasoning_settings_only_for_reasoning_models():
    gpt5 = model_settings("gpt-5-mini")
    assert gpt5.tool_choice == "required"
    assert gpt5.reasoning and gpt5.reasoning.effort == get_settings().azure_reasoning_effort
    assert gpt5.verbosity == get_settings().azure_verbosity
    gpt4 = model_settings("gpt-4o-mini")
    assert gpt4.reasoning is None and gpt4.verbosity is None
