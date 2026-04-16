"""Stage 4 tests for MCPHub confirmation and structured failures."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.mcp.security import PermissionLevel


class FakeMCPClient(MCPClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict]] = []
        self.tools = {"file_write"}

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools

    def list_tool_names(self) -> list[str]:
        return list(self.tools)

    async def call_tool(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        return f"{tool_name} ok"


def _hub(tmp_path) -> MCPHub:
    client = FakeMCPClient()
    security = SecurityManager()
    security.register_tool("file_write", [PermissionLevel.WRITE])
    return MCPHub(
        client=client,
        planner=DAGPlanner(),
        security=security,
        audit=AuditLogger(log_dir=str(tmp_path)),
    )


@pytest.mark.asyncio
async def test_ask_decision_creates_pending_confirmation(tmp_path):
    hub = _hub(tmp_path)
    context = SimpleNamespace(mode="daily_mode")

    result = await hub.execute_single(
        "file_write",
        {"path": "note.txt", "content": "hello"},
        context=context,
        inferred_intent="写文件",
    )

    assert result["pending_confirmation"] is True
    assert result["confirmation_id"]
    assert hub.has_pending_confirmations()
    assert hub.client.calls == []


@pytest.mark.asyncio
async def test_approve_pending_executes_original_tool(tmp_path):
    hub = _hub(tmp_path)
    context = SimpleNamespace(mode="daily_mode")
    await hub.execute_single(
        "file_write",
        {"path": "note.txt", "content": "hello"},
        context=context,
        inferred_intent="写文件",
    )

    chain = await hub.approve_latest_pending(context)

    assert chain.results[0]["is_error"] is False
    assert "file_write ok" in chain.results[0]["content"]
    assert hub.client.calls == [("file_write", {"path": "note.txt", "content": "hello"})]
    assert not hub.has_pending_confirmations()


@pytest.mark.asyncio
async def test_unknown_tool_is_structured_error_not_exception(tmp_path):
    hub = _hub(tmp_path)
    context = SimpleNamespace(mode="daily_mode")

    result = await hub.execute_single("missing_tool", {}, context=context)

    assert result["is_error"] is True
    assert result["error_type"] == "unknown_tool"
    assert "未知工具" in result["error"]
