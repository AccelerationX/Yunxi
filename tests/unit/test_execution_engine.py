"""ExecutionEngine 单元测试。"""

import pytest

from core.execution.engine import ConversationContext, EngineConfig, ExecutionResult
from core.llm.adapter import LLMAdapter
from core.types.message_types import (
    AssistantMessage,
    TextContentBlock,
    ToolResultContentBlock,
    UserMessage,
)


def test_conversation_context_add_and_trim():
    ctx = ConversationContext(limit=4)
    ctx.add_user_message("A")
    ctx.add_assistant_message("B")
    ctx.add_user_message("C")
    ctx.add_assistant_message("D")
    ctx.add_user_message("E")

    msgs = ctx.get_messages()
    assert len(msgs) == 4
    # 最早的消息 A 被截断
    assert isinstance(msgs[0], AssistantMessage)
    assert isinstance(msgs[-1], UserMessage)


def test_conversation_context_tool_results():
    ctx = ConversationContext(limit=10)
    ctx.add_user_message("帮我截图")
    ctx.add_tool_results([
        ToolResultContentBlock(tool_use_id="t1", content="截图成功", is_error=False),
    ])

    msgs = ctx.get_messages()
    assert len(msgs) == 2
    assert isinstance(msgs[1], UserMessage)


def test_execution_result_defaults():
    result = ExecutionResult(content="你好")
    assert result.content == "你好"
    assert result.tool_calls_used == []
    assert result.skill_used is None
    assert result.error is None


def test_engine_config_defaults():
    cfg = EngineConfig()
    assert cfg.max_turns == 10
    assert cfg.recent_message_limit == 20
    assert cfg.enable_tool_use is True
    assert cfg.enable_skill_fastpath is True


def test_ollama_adapter_from_env_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    adapter = LLMAdapter.from_env("ollama")

    assert adapter.provider.config.provider == "ollama"
    assert adapter.provider.config.api_key == ""
    assert adapter.provider.config.model == "qwen3:4b"
    assert adapter.provider.config.base_url == "http://localhost:11434"
