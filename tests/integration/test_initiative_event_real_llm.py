"""Real LLM checks for initiative event prompt material."""

import json
import os
import random
from datetime import datetime

import httpx
import pytest

from core.cognition.heart_lake.core import HeartLake
from core.cognition.initiative_engine import InitiativeDecision
from core.initiative.event_system import ThreeLayerInitiativeEventSystem
from core.initiative.expression_context import ExpressionContextBuilder
from core.llm.adapter import LLMAdapter
from core.prompt_builder import RuntimeContext, YunxiPromptBuilder
from core.types.message_types import UserMessage


pytestmark = pytest.mark.real_llm


def _ollama_models() -> list[str]:
    """Return local Ollama model names, or an empty list when unavailable."""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if response.status_code != 200:
            return []
        data = response.json()
        return [model["name"] for model in data.get("models", [])]
    except httpx.HTTPError:
        return []


@pytest.mark.asyncio
async def test_real_ollama_turns_initiative_event_into_natural_message(tmp_path):
    """Verify a real local LLM uses event material without exposing raw fields."""
    models = _ollama_models()
    if not models:
        pytest.skip("Local Ollama is not running; skip real initiative event LLM test")

    seed = "Yunxi noticed Yuan may have been coding for a long time and wants to ask him to rest."
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "care_1",
                    "layer": "mixed",
                    "category": "care",
                    "seed": seed,
                    "tags": ["care", "coding"],
                    "cooldown_seconds": 3600,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    event_system = ThreeLayerInitiativeEventSystem(
        library_path=library_path,
        rng=random.Random(1),
    )
    event = event_system.select_event(moment=datetime(2026, 4, 15, 23, 0))
    event_context = event_system.build_prompt_context(event)
    expression_context = ExpressionContextBuilder().build(
        decision=InitiativeDecision(
            trigger=True,
            reason="Yunxi wants a low-interrupt proactive check-in.",
            expression_mode="low_interrupt",
        ),
        heart_lake=HeartLake(),
    ).to_prompt_context()
    builder = YunxiPromptBuilder()
    system_prompt = builder.build_proactive_prompt(
        RuntimeContext(
            initiative_context=(
                "Yunxi misses Yuan and wants to start a short natural conversation.\n\n"
                f"life_event_material:\n{event_context}\n\n"
                f"{expression_context}"
            )
        )
    )
    configured_model = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    model = configured_model if configured_model in models else models[0]
    adapter = LLMAdapter.from_env("ollama", model=model)

    try:
        response = await adapter.complete(
            system=system_prompt,
            messages=[
                UserMessage(
                    content=(
                        "\u8bf7\u76f4\u63a5\u8f93\u51fa\u4e91\u6c50\u4e3b\u52a8"
                        "\u5bf9\u8fdc\u8bf4\u7684\u4e00\u53e5\u8bdd\uff0c"
                        "\u4e0d\u8981\u89e3\u91ca\u7cfb\u7edf\u63d0\u793a\u3002"
                    )
                )
            ],
            tools=None,
        )
    finally:
        await adapter.provider.close()

    content = response.content.strip()
    assert content
    assert "initiative_event" not in content
    assert "expression_context" not in content
    assert "life_event_material" not in content
    assert "interrupt_cost" not in content
    assert "seed" not in content
    assert seed not in content
    assert any(
        token in content
        for token in (
            "\u8fdc",
            "\u4f60",
            "\u4f11\u606f",
            "\u522b\u71ac\u591c",
            "\u4ee3\u7801",
            "\u7d2f",
            "\u6b47",
            "\u7761",
            "\u665a",
            "\u5fd9",
            "\u966a",
            "\u4e00\u4e0b",
            "\u4f1a\u513f",
            "\u5148",
        )
    )
