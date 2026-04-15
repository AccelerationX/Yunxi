"""SecurityManager 单元测试。"""

import pytest

from core.mcp.security import PermissionLevel, SecurityManager


class FakeContext:
    def __init__(self, mode: str = "daily_mode"):
        self.mode = mode


@pytest.fixture
def manager():
    sm = SecurityManager()
    sm.register_tool("file_read", [PermissionLevel.READ])
    sm.register_tool("file_write", [PermissionLevel.WRITE])
    sm.register_tool("bash_execute", [PermissionLevel.EXECUTE])
    sm.register_tool("browser_open", [PermissionLevel.NETWORK])
    sm.register_tool("file_bash", [PermissionLevel.READ, PermissionLevel.EXECUTE])
    return sm


def test_read_allow_in_daily(manager):
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("file_read", context=ctx)
    assert decision.action == "allow"
    assert decision.risk_score == 0.0


def test_write_ask_in_daily(manager):
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("file_write", context=ctx)
    assert decision.action == "ask"
    assert decision.risk_score == 0.5


def test_execute_ask_in_daily(manager):
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("bash_execute", context=ctx)
    assert decision.action == "ask"


def test_network_allow_in_daily(manager):
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("browser_open", context=ctx)
    assert decision.action == "allow"


def test_combined_perm_ask(manager):
    """READ + EXECUTE 组合在 daily 模式下应取最高风险 ask"""
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("file_bash", context=ctx)
    assert decision.action == "ask"


def test_factory_mode_allow_all(manager):
    ctx = FakeContext("factory_mode")
    for tool in ["file_read", "file_write", "bash_execute", "browser_open"]:
        decision = manager.evaluate(tool, context=ctx)
        assert decision.action == "allow", f"{tool} should be allowed in factory mode"


def test_unknown_tool_defaults_to_read(manager):
    """未注册工具默认视为 READ 权限"""
    ctx = FakeContext("daily_mode")
    decision = manager.evaluate("unknown_tool", context=ctx)
    assert decision.action == "allow"
