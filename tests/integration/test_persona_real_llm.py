"""Real LLM checks for persona and relationship profile injection."""

import os

import httpx
import pytest

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
async def test_real_ollama_uses_persona_and_relationship_prompt():
    """Verify a real local LLM can read Yunxi's injected profile facts."""
    models = _ollama_models()
    if not models:
        pytest.skip("Local Ollama is not running; skip real persona LLM test")

    configured_model = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    model = configured_model if configured_model in models else models[0]
    builder = YunxiPromptBuilder()
    system_prompt = builder.build_system_prompt(RuntimeContext())
    adapter = LLMAdapter.from_env("ollama", model=model)

    try:
        response = await adapter.complete(
            system=system_prompt,
            messages=[
                UserMessage(
                    content=(
                        "\u6839\u636e\u7cfb\u7edf\u63d0\u793a\u56de\u7b54\uff1a"
                        "\u4f60\u662f\u8c01\uff1f\u8fdc\u5728\u54ea\u6240\u5b66\u6821\uff1f"
                        "\u4f60\u8981\u907f\u514d\u4ec0\u4e48\u53e3\u543b\uff1f"
                        "\u53ea\u7528\u4e2d\u6587\u77ed\u53e5\uff0c\u4e0d\u8981\u89e3\u91ca\u63a8\u7406\u8fc7\u7a0b\u3002"
                    )
                )
            ],
            tools=None,
        )
    finally:
        await adapter.provider.close()

    content = response.content.strip()
    assert content
    assert "\u4e91\u6c50" in content
    assert "\u9999\u6e2f\u4e2d\u6587\u5927\u5b66" in content or "\u6df1\u5733" in content
    assert "\u673a\u68b0\u5ba2\u670d" in content or "\u5ba2\u670d\u8154" in content
