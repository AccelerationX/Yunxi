"""端到端真实 LLM + MCPHub 集成测试。

验证 YunxiRuntime 能正确调用真实 LLM（MiniMax/Moonshot），
并通过 MCPHub 执行 Desktop Server 的截图工具。

注意：本测试需要有效的 LLM API key 和网络连接。
"""

import asyncio
import os
import sys
import tempfile

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.llm.adapter import LLMAdapter
from core.mcp import MCPClient, MCPHub, DAGPlanner, SecurityManager, AuditLogger
from core.mcp.security import PermissionLevel
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.runtime import YunxiRuntime
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator


def _load_env() -> None:
    """从 .env 文件加载环境变量（仅用于测试）。"""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in os.environ:
                os.environ[key] = value


@pytest_asyncio.fixture
async def llm_runtime():
    _load_env()

    # 使用 Moonshot (Kimi) 进行端到端测试，因其 function calling 更稳定
    provider_name = "moonshot"
    if not os.environ.get("MOONSHOT_API_KEY"):
        pytest.skip("缺少 MOONSHOT_API_KEY，跳过真实 LLM 测试")

    adapter = LLMAdapter.from_env(provider_name)

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
    hub.security.register_tool_override("screenshot_capture", "daily_mode", "allow")
    hub.security.register_tool_override("clipboard_write", "daily_mode", "allow")

    prompt_builder = YunxiPromptBuilder(PromptConfig())
    memory = MemoryManager(base_path=tempfile.mkdtemp())
    await memory.initialize()
    engine = YunxiExecutionEngine(
        llm=adapter,
        mcp_hub=hub,
        memory_manager=memory,
        config=EngineConfig(max_turns=5, enable_tool_use=True),
    )
    heart_lake = HeartLake()
    perception = PerceptionCoordinator()

    runtime = YunxiRuntime(
        engine=engine,
        prompt_builder=prompt_builder,
        heart_lake=heart_lake,
        perception=perception,
        memory=memory,
        mcp_hub=hub,
    )

    yield runtime

    await hub.client.disconnect_all()


@pytest.mark.asyncio
async def test_real_llm_screenshot_tool_call(llm_runtime):
    """真实 LLM 识别截图意图并调用 screenshot_capture。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "e2e_screenshot.png")
        # 使用明确的指令，降低 LLM 不调用工具的概率
        user_input = f"帮我截取屏幕并保存到 {save_path}"
        response = await llm_runtime.chat(user_input)

        # 断言 1：LLM 最终返回了字符串（无论工具结果如何，不崩溃）
        assert isinstance(response, str)

        # 断言 2：截图文件确实被创建了（说明 tool call 被执行）
        assert os.path.exists(save_path), (
            f"截图文件未生成，可能 LLM 未调用工具或工具执行失败。"
            f"LLM 回复：{response}"
        )
        assert os.path.getsize(save_path) > 0


@pytest.mark.asyncio
async def test_real_llm_clipboard_roundtrip(llm_runtime):
    """真实 LLM 识别剪贴板操作意图并调用 clipboard_read/write。"""
    test_text = "云汐3.0端到端测试"
    # 先写入剪贴板
    write_response = await llm_runtime.chat(f"帮我把 '{test_text}' 写入剪贴板")
    assert isinstance(write_response, str)

    # 再读取剪贴板
    read_response = await llm_runtime.chat("帮我读取剪贴板内容")
    assert isinstance(read_response, str)
    assert test_text in read_response, (
        f"剪贴板内容未出现在 LLM 回复中。"
        f"read_response: {read_response}"
    )
