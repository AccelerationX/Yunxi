"""Stage 4 ExecutionEngine behavior tests."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel


@dataclass
class FakeResponse:
    content: str = ""
    tool_calls: list[Any] | None = None


class FailingLLM:
    async def complete(self, *args, **kwargs):
        raise RuntimeError("All connection attempts failed")


class ToolCallingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(
            content="",
            tool_calls=[
                SimpleNamespace(
                    id="call_1",
                    name="file_write",
                    arguments={"path": "note.txt", "content": "hello"},
                )
            ],
        )


class FinalizingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(content="好啦，已经自然处理好了。")


class FakeClient(MCPClient):
    def __init__(self) -> None:
        super().__init__()
        self.tools = {"file_write"}
        self.calls: list[tuple[str, dict]] = []

    async def get_tool_descriptions_for_llm(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "file_write",
                    "description": "write file",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools

    async def call_tool(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        return "done"


class FakeMemory:
    def __init__(self, skill: dict | None = None) -> None:
        self.skill = skill
        self.outcomes = []
        self.experiences = []

    async def try_skill(self, user_input: str):
        return self.skill

    def record_skill_outcome(self, skill_name: str, success: bool) -> None:
        self.outcomes.append((skill_name, success))

    def record_experience(self, **kwargs) -> None:
        self.experiences.append(kwargs)


def _hub(tmp_path, *, allow_write: bool = False) -> MCPHub:
    client = FakeClient()
    security = SecurityManager()
    security.register_tool("file_write", [PermissionLevel.WRITE])
    if allow_write:
        security.register_tool_override("file_write", "daily_mode", "allow")
    hub = MCPHub(
        client=client,
        planner=DAGPlanner(),
        security=security,
        audit=AuditLogger(log_dir=str(tmp_path)),
    )
    hub._initialized = True
    return hub


@pytest.mark.asyncio
async def test_llm_exception_returns_personalized_message(tmp_path):
    engine = YunxiExecutionEngine(
        llm=FailingLLM(),
        mcp_hub=_hub(tmp_path),
        memory_manager=FakeMemory(),
        config=EngineConfig(enable_tool_use=False, enable_skill_fastpath=False),
    )

    result = await engine.respond("你好", "system", SimpleNamespace(mode="daily_mode"))

    assert "云汐这里出了点小问题" not in result.content
    assert "All connection attempts failed" not in result.content
    assert "卡了一下" in result.content
    assert result.error == "All connection attempts failed"


@pytest.mark.asyncio
async def test_tool_ask_creates_natural_confirmation_then_approval(tmp_path):
    hub = _hub(tmp_path)
    engine = YunxiExecutionEngine(
        llm=ToolCallingLLM(),
        mcp_hub=hub,
        memory_manager=FakeMemory(),
        config=EngineConfig(max_turns=1, enable_tool_use=True, enable_skill_fastpath=False),
    )
    context = SimpleNamespace(mode="daily_mode")

    first = await engine.respond("帮我写个文件", "system", context)
    second = await engine.respond("确认", "system", context)

    assert "点头" in first.content
    assert "工具执行遇到问题" not in first.content
    assert "已经按你点头" in second.content
    assert hub.client.calls == [("file_write", {"path": "note.txt", "content": "hello"})]


@pytest.mark.asyncio
async def test_skill_fastpath_uses_llm_finalization(tmp_path):
    skill = {
        "skill_name": "write_note",
        "actions": [
            {"tool": "file_write", "args": {"path": "note.txt", "content": "hello"}}
        ],
    }
    llm = FinalizingLLM()
    engine = YunxiExecutionEngine(
        llm=llm,
        mcp_hub=_hub(tmp_path, allow_write=True),
        memory_manager=FakeMemory(skill=skill),
        config=EngineConfig(enable_tool_use=True, enable_skill_fastpath=True),
    )

    result = await engine.respond("写一下", "system", SimpleNamespace(mode="daily_mode"))

    assert result.content == "好啦，已经自然处理好了。"
    assert result.skill_used == "write_note"
    assert llm.calls == 1
