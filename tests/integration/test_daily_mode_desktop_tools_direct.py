"""Direct daily-mode desktop tool validation without Feishu.

These tests keep the same user-facing flow as live daily mode:
user asks Yunxi to do something, Yunxi asks for confirmation when the tool is
WRITE/EXECUTE, and the test simulates the user's "确认" reply.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio

from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel
from core.types.message_types import ToolResultContentBlock, UserMessage


pytestmark = pytest.mark.desktop_mcp


@dataclass
class FakeResponse:
    content: str = ""
    tool_calls: list[Any] | None = None


class OneToolLLM:
    """Script one tool call for the first LLM turn."""

    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.calls = 0

    async def complete(self, *args, **kwargs) -> FakeResponse:
        self.calls += 1
        return FakeResponse(
            tool_calls=[
                SimpleNamespace(
                    id=f"call_{self.tool_name}",
                    name=self.tool_name,
                    arguments=self.arguments,
                )
            ]
        )


class FakeMemory:
    async def try_skill(self, user_input: str):
        return None

    def record_experience(self, **kwargs) -> None:
        return None


@pytest_asyncio.fixture
async def desktop_hub(tmp_path):
    client = MCPClient(timeout_seconds=45.0)
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=str(tmp_path / "audit"))
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

    project_root = Path(__file__).resolve().parents[2]
    server_path = project_root / "src" / "core" / "mcp" / "servers" / "desktop_server.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    await hub.initialize(
        [
            {
                "name": "desktop",
                "command": sys.executable,
                "args": ["-u", str(server_path)],
                "env": env,
                "permissions": {
                    "screenshot_capture": [PermissionLevel.WRITE.value],
                    "clipboard_read": [PermissionLevel.READ.value],
                    "clipboard_write": [PermissionLevel.WRITE.value],
                    "desktop_notify": [PermissionLevel.WRITE.value],
                    "app_launch_ui": [PermissionLevel.EXECUTE.value],
                    "window_focus_ui": [PermissionLevel.EXECUTE.value],
                    "window_minimize_ui": [PermissionLevel.EXECUTE.value],
                },
            }
        ]
    )
    try:
        yield hub
    finally:
        await hub.client.disconnect_all()


async def _ask_and_confirm(
    hub: MCPHub,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, str, YunxiExecutionEngine]:
    engine = YunxiExecutionEngine(
        llm=OneToolLLM(tool_name, arguments),
        mcp_hub=hub,
        memory_manager=FakeMemory(),
        config=EngineConfig(
            max_turns=1,
            enable_tool_use=True,
            enable_skill_fastpath=False,
        ),
    )
    context = SimpleNamespace(mode="daily_mode")

    first = await engine.respond(f"请使用 {tool_name}", "system", context)
    second = await engine.respond("确认", "system", context)

    return first.content, second.content, engine


def _latest_tool_result(engine: YunxiExecutionEngine) -> str:
    for message in reversed(engine.context.get_messages()):
        if not isinstance(message, UserMessage):
            continue
        content = message.content
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, ToolResultContentBlock):
                return block.content
    return ""


def _assert_tool_result_ok(engine: YunxiExecutionEngine) -> str:
    content = _latest_tool_result(engine)
    assert content
    assert "[错误" not in content
    assert "失败" not in content
    assert "未找到" not in content
    return content


@pytest.mark.asyncio
async def test_yunxi_direct_clipboard_write_and_read(desktop_hub):
    first, second, engine = await _ask_and_confirm(
        desktop_hub,
        "clipboard_write",
        {"text": "yunxi direct clipboard matrix"},
    )

    assert "点头" in first
    assert "已经按你点头" in second
    assert "已写入" in _assert_tool_result_ok(engine)

    read_result = await desktop_hub.execute_single(
        "clipboard_read",
        {},
        context=SimpleNamespace(mode="daily_mode"),
    )
    assert "yunxi direct clipboard matrix" in read_result.get("content", "")


@pytest.mark.asyncio
async def test_yunxi_direct_screenshot_capture(desktop_hub, tmp_path):
    path = tmp_path / "yunxi_direct_screenshot.png"

    first, second, engine = await _ask_and_confirm(
        desktop_hub,
        "screenshot_capture",
        {"save_path": str(path)},
    )

    assert "点头" in first
    assert "已经按你点头" in second
    assert "截图已保存" in _assert_tool_result_ok(engine)
    assert path.exists()
    assert path.stat().st_size > 0


@pytest.mark.asyncio
async def test_yunxi_direct_desktop_notify(desktop_hub):
    first, second, engine = await _ask_and_confirm(
        desktop_hub,
        "desktop_notify",
        {"title": "云汐工具验收", "message": "desktop_notify direct matrix"},
    )

    assert "点头" in first
    assert "已经按你点头" in second
    assert "通知已发送" in _assert_tool_result_ok(engine)


@pytest.mark.asyncio
async def test_yunxi_direct_launch_focus_and_minimize_notepad(desktop_hub):
    try:
        first, second, engine = await _ask_and_confirm(
            desktop_hub,
            "app_launch_ui",
            {"app_name": "notepad"},
        )
        assert "点头" in first
        assert "已经按你点头" in second
        assert "成功启动" in _assert_tool_result_ok(engine)

        await asyncio.sleep(1.0)
        focus_first, focus_second, focus_engine = await _ask_and_confirm(
            desktop_hub,
            "window_focus_ui",
            {"window_title_keyword": "Notepad"},
        )
        assert "点头" in focus_first
        assert "已经按你点头" in focus_second
        assert "已聚焦窗口" in _assert_tool_result_ok(focus_engine)

        minimize_first, minimize_second, minimize_engine = await _ask_and_confirm(
            desktop_hub,
            "window_minimize_ui",
            {"window_title_keyword": "Notepad"},
        )
        assert "点头" in minimize_first
        assert "已经按你点头" in minimize_second
        assert "已最小化窗口" in _assert_tool_result_ok(minimize_engine)
    finally:
        subprocess.run(
            ["taskkill", "/IM", "notepad.exe", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
