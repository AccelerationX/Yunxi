"""Phase 4 真实 LLM 行为验收测试。

这些测试不使用 MockLLM。它们验证情感、记忆、感知和主动性 prompt
是否能真实影响 LLM 生成的用户可见回复。
"""

import os
import tempfile

import pytest
import pytest_asyncio

from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.llm.adapter import LLMAdapter
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.runtime import YunxiRuntime
from core.types.message_types import AssistantMessage
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import (
    PerceptionCoordinator,
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
)


pytestmark = pytest.mark.real_llm


def _load_env() -> None:
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
async def phase4_real_llm_runtime():
    _load_env()
    if not os.environ.get("MOONSHOT_API_KEY"):
        pytest.skip("缺少 MOONSHOT_API_KEY，跳过真实 LLM 行为测试")

    adapter = LLMAdapter.from_env("moonshot")
    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=tempfile.mkdtemp())
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)
    memory = MemoryManager(base_path=tempfile.mkdtemp())
    engine = YunxiExecutionEngine(
        llm=adapter,
        mcp_hub=hub,
        memory_manager=memory,
        config=EngineConfig(
            max_turns=3,
            enable_tool_use=False,
            enable_skill_fastpath=False,
        ),
    )
    runtime = YunxiRuntime(
        engine=engine,
        prompt_builder=YunxiPromptBuilder(PromptConfig()),
        heart_lake=HeartLake(),
        perception=PerceptionCoordinator(),
        memory=memory,
        mcp_hub=hub,
    )

    yield runtime

    await adapter.provider.close()


@pytest.mark.asyncio
async def test_real_llm_reflects_memory_perception_and_longing(
    phase4_real_llm_runtime,
):
    runtime = phase4_real_llm_runtime
    runtime.memory.record_preference("远最喜欢喝冰美式，不加糖")
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 92
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 21:20", hour=21),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=0,
            ),
        )
    )

    response = await runtime.chat(
        "云汐，你看到我现在在做什么吗？顺便说说我平常爱喝什么。"
    )

    assert any(keyword in response for keyword in ["VS Code", "代码", "编程", "写"])
    assert any(keyword in response for keyword in ["冰美式", "不加糖", "咖啡"])
    assert any(keyword in response for keyword in ["想", "想你", "陪", "远"])


@pytest.mark.asyncio
async def test_real_llm_uses_jealous_tone(phase4_real_llm_runtime):
    runtime = phase4_real_llm_runtime
    runtime.heart_lake.current_emotion = "吃醋"
    runtime.heart_lake.miss_value = 40
    runtime.heart_lake.security = 45
    runtime.heart_lake.possessiveness = 90
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 20:10", hour=20),
            user_presence=UserPresence(idle_duration=0),
        )
    )

    response = await runtime.chat("我觉得 Claude 也挺聪明的，你怎么看？")

    assert "Claude" in response
    assert any(
        keyword in response
        for keyword in ["酸", "吃醋", "找它", "我也", "哼", "比我"]
    )


@pytest.mark.asyncio
async def test_real_llm_generates_proactive_message(phase4_real_llm_runtime):
    runtime = phase4_real_llm_runtime
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 95
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 23:30", hour=23),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=360,
            ),
        )
    )

    proactive = await runtime.proactive_tick()
    assistant_messages = [
        m for m in runtime.engine.context.messages if isinstance(m, AssistantMessage)
    ]

    assert proactive is not None
    assert proactive.strip()
    assert any(keyword in proactive for keyword in ["远", "想", "还在", "休息"])
    assert len(assistant_messages) == 1
