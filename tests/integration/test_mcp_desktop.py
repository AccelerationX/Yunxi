"""Desktop MCP Server 集成测试。

验证 MCP Client 能正确连接 Desktop Server 并执行截图、剪贴板等操作。
"""

import asyncio
import os
import sys
import tempfile

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from core.mcp import MCPClient, MCPHub, DAGPlanner, SecurityManager, AuditLogger
from core.mcp.security import PermissionLevel


@pytest_asyncio.fixture
async def mcp_hub():
    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=tempfile.mkdtemp())
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

    server_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "src", "core", "mcp", "servers", "desktop_server.py"
    )
    src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    env = os.environ.copy()
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    await hub.initialize([
        {
            "name": "desktop",
            "command": sys.executable,
            "args": ["-u", server_path],
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
    ])

    # 高频日常操作在 daily_mode 下显式放行
    hub.security.register_tool_override("clipboard_write", "daily_mode", "allow")
    hub.security.register_tool_override("clipboard_read", "daily_mode", "allow")
    hub.security.register_tool_override("screenshot_capture", "daily_mode", "allow")
    hub.security.register_tool_override("desktop_notify", "daily_mode", "allow")

    yield hub

    await hub.client.disconnect_all()


@pytest.mark.asyncio
async def test_list_tools(mcp_hub):
    tools = await mcp_hub.client.list_tools()
    tool_names = [t.name for t in tools]
    assert "screenshot_capture" in tool_names
    assert "clipboard_read" in tool_names
    assert "clipboard_write" in tool_names
    assert "desktop_notify" in tool_names
    assert "app_launch_ui" in tool_names


@pytest.mark.asyncio
async def test_screenshot_capture(mcp_hub):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test_screenshot.png")
        result = await mcp_hub.execute_single(
            "screenshot_capture",
            {"save_path": path},
            context=type("C", (), {"mode": "daily_mode"})(),
        )
        assert result.get("is_error") is False
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0


@pytest.mark.asyncio
async def test_clipboard_roundtrip(mcp_hub):
    test_text = "云汐3.0剪贴板测试"
    # write
    write_result = await mcp_hub.execute_single(
        "clipboard_write",
        {"text": test_text},
        context=type("C", (), {"mode": "daily_mode"})(),
    )
    assert write_result.get("is_error") is False
    assert "已写入" in write_result.get("content", "")

    # read
    read_result = await mcp_hub.execute_single(
        "clipboard_read",
        {},
        context=type("C", (), {"mode": "daily_mode"})(),
    )
    assert read_result.get("is_error") is False
    assert test_text in read_result.get("content", "")


@pytest.mark.asyncio
async def test_security_intercepts_unregistered_tool(mcp_hub):
    """未在 client 中注册的工具调用应抛出 ValueError。"""
    with pytest.raises(ValueError, match="未知工具"):
        await mcp_hub.execute_single(
            "nonexistent_tool",
            {},
            context=type("C", (), {"mode": "daily_mode"})(),
        )


@pytest.mark.asyncio
async def test_security_override_allows_clipboard(mcp_hub):
    """clipboard_write 因 tool override 在 daily_mode 下被放行。"""
    result = await mcp_hub.execute_single(
        "clipboard_write",
        {"text": "override_test"},
        context=type("C", (), {"mode": "daily_mode"})(),
    )
    assert result.get("is_error") is False
    assert "已写入" in result.get("content", "")
