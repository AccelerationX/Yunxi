"""真实 Ollama LLM 集成测试。"""

import os

import httpx
import pytest

from core.llm.adapter import LLMAdapter
from core.types.message_types import UserMessage


def _ollama_models() -> list[str]:
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if response.status_code != 200:
            return []
        data = response.json()
        return [model["name"] for model in data.get("models", [])]
    except httpx.HTTPError:
        return []


@pytest.mark.asyncio
async def test_real_ollama_chat_completion():
    """验证本地 Ollama OpenAI-compatible chat/completions 路径可用。"""
    models = _ollama_models()
    if not models:
        pytest.skip("本机 Ollama 未启动，跳过真实本地 LLM 测试")

    configured_model = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    model = configured_model if configured_model in models else models[0]
    adapter = LLMAdapter.from_env("ollama", model=model)
    try:
        response = await adapter.complete(
            system="你是云汐，用一句中文自然回复，不要输出推理过程。",
            messages=[UserMessage(content="你现在是本地模型在运行吗？")],
            tools=None,
        )
    finally:
        await adapter.provider.close()

    assert response.content.strip()
    assert any(token in response.content for token in ("本地", "云汐", "运行", "模型"))
