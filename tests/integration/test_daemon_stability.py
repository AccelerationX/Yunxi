"""长时间 Daemon 稳定性测试。

多轮 chat() + proactive_tick() 循环，验证：
- continuity 持久化正常
- memory 无泄漏
- heart_lake 状态合理

CI 友好：通过 STABILITY_TEST_MINUTES 环境变量控制测试时长。
- 默认 1 分钟（快速验证）
- CI 可设为 5 分钟
- 完整稳定性测试可设为 30 分钟
"""

import os
import shutil
from pathlib import Path

import pytest

from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.initiative.continuity import CompanionContinuityService
from core.initiative.event_system import ThreeLayerInitiativeEventSystem
from core.llm.adapter import LLMAdapter
from core.mcp import AuditLogger, DAGPlanner, MCPClient, MCPHub, SecurityManager
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.runtime import YunxiRuntime
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import (
    PerceptionCoordinator,
    PerceptionSnapshot,
    SystemState,
    TimeContext,
    UserPresence,
)


# 测试消息轮转库
TEST_MESSAGES = [
    "你好呀",
    "今天天气怎么样？",
    "你在干嘛呢",
    "我刚吃完午饭",
    "有点想你了",
    "陪我聊会儿天吧",
    "给我讲个笑话好不好？",
    "晚上有什么计划吗？",
]


class StaticPerceptionProvider:
    """稳定性测试专用感知提供者，不读取真实 Windows 桌面。"""

    def __init__(self) -> None:
        self.snapshot = PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 10:00", hour=10),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=0,
                is_at_keyboard=True,
            ),
            system_state=SystemState(cpu_percent=12.0),
        )

    def fetch(self) -> PerceptionSnapshot:
        """返回固定快照，避免稳定性测试被真实桌面感知卡住。"""
        return self.snapshot


class MockLLM:
    """简单 Mock LLM，返回固定回复避免真实 LLM 调用。"""

    def __init__(self):
        self.call_count = 0
        self.history = []

    async def complete(self, system: str, messages: list, tools=None):
        self.call_count += 1
        self.history.append({"system": system, "messages": messages})
        # 返回一个带 tool_calls 属性的响应对象
        response = MockResponse(
            content=f"云汐回复 #{self.call_count}：好的，我在呢～"
        )
        return response


class MockResponse:
    """Mock LLM 响应。"""

    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


@pytest.fixture
def stability_runtime(tmp_path):
    """构建用于稳定性测试的 Runtime。"""
    mock_llm = MockLLM()

    event_lib = tmp_path / "life_events.json"
    real_lib = Path("data/initiative/life_events.json")
    if real_lib.exists():
        shutil.copy(real_lib, event_lib)
    else:
        event_lib.write_text(
            '[{"id":"test","layer":"inner_life","category":"test","seed":"test","tags":[],"cooldown_seconds":3600}]',
            encoding="utf-8",
        )

    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=str(tmp_path / "audit"))

    memory = MemoryManager(
        base_path=str(tmp_path / "memory"),
        embedding_provider="lexical",
    )

    continuity_path = tmp_path / "continuity.json"

    engine = YunxiExecutionEngine(
        llm=mock_llm,
        mcp_hub=MCPHub(client=client, planner=planner, security=security, audit=audit),
        memory_manager=memory,
        config=EngineConfig(
            max_turns=2,
            enable_tool_use=False,
            enable_skill_fastpath=False,
        ),
    )

    runtime = YunxiRuntime(
        engine=engine,
        prompt_builder=YunxiPromptBuilder(PromptConfig()),
        heart_lake=HeartLake(),
        perception=PerceptionCoordinator(provider=StaticPerceptionProvider()),
        memory=memory,
        continuity=CompanionContinuityService(storage_path=continuity_path),
        initiative_event_system=ThreeLayerInitiativeEventSystem(
            library_path=str(event_lib),
            state_path=tmp_path / "initiative_event_state.json",
        ),
    )

    return runtime, mock_llm, continuity_path


@pytest.mark.asyncio
async def test_stability_continuity_persistence(stability_runtime):
    """验证 continuity 持久化在多轮对话后仍然正常。"""
    runtime, mock_llm, continuity_path = stability_runtime

    # 执行多轮对话
    for i in range(10):
        await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])

    # 检查 continuity 文件存在且有内容
    assert continuity_path.exists(), "Continuity 文件未生成"

    with open(continuity_path, encoding="utf-8") as f:
        import json
        data = json.load(f)

    assert data.get("exchanges") is not None, "Exchanges 未保存"
    assert len(data.get("exchanges", [])) == 10, f"Expected 10 exchanges, got {len(data.get('exchanges', []))}"


@pytest.mark.asyncio
async def test_stability_memory_no_leak(stability_runtime):
    """验证 memory 在多轮操作后不会泄漏。"""
    runtime, mock_llm, _ = stability_runtime

    initial_prefs = len(runtime.memory._preferences)
    initial_episodes = len(runtime.memory._episodes)

    # 执行多轮对话（每轮注入一个记忆）
    for i in range(5):
        runtime.memory.record_preference(f"测试偏好 {i}")
        runtime.memory.record_episode(f"测试经历 {i}")
        await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])

    # 验证记忆数量合理增长
    assert len(runtime.memory._preferences) == initial_prefs + 5
    assert len(runtime.memory._episodes) == initial_episodes + 5


@pytest.mark.asyncio
async def test_stability_heart_lake_reasonable(stability_runtime):
    """验证 heart_lake 状态在多轮交互后保持合理。"""
    runtime, mock_llm, _ = stability_runtime

    # 初始状态
    assert 0 <= runtime.heart_lake.miss_value <= 100
    assert 0 <= runtime.heart_lake.security <= 100

    # 执行多轮对话
    for i in range(5):
        await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])

    # 交互后想念值应该回落
    assert runtime.heart_lake.miss_value <= 50, "想念值异常升高"


@pytest.mark.asyncio
async def test_stability_proactive_tick_loop(stability_runtime):
    """验证 proactive_tick 在连续调用下不崩溃。"""
    runtime, mock_llm, _ = stability_runtime

    # 设置高想念值触发主动
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 95

    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 23:30", hour=23),
            user_presence=UserPresence(idle_duration=360),
        )
    )

    # 连续触发多次 proactive
    for _ in range(5):
        # 重置 cooldown
        runtime.initiative_engine.reset_cooldown()
        runtime.initiative_engine._last_trigger_time = None

        proactive = await runtime.proactive_tick()
        # proactive 可能为 None（cooldown 或预算耗尽），但调用不应崩溃


@pytest.mark.asyncio
async def test_stability_message_context_limit(stability_runtime):
    """验证消息上下文在长时间运行后仍然有限制。"""
    runtime, mock_llm, _ = stability_runtime

    # 快速执行 20 轮对话
    for i in range(20):
        await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])

    # 检查 engine context 消息数量不超过限制
    message_count = len(runtime.engine.context.messages)
    assert message_count <= EngineConfig().recent_message_limit * 2, \
        f"消息数量 {message_count} 超过预期限制"


@pytest.mark.asyncio
async def test_stability_continuous_chat_rounds(stability_runtime):
    """核心稳定性：连续多轮 chat 调用不崩溃。"""
    runtime, mock_llm, _ = stability_runtime

    # 获取测试时长配置
    test_minutes = int(os.environ.get("STABILITY_TEST_MINUTES", "1"))
    rounds_per_minute = 10
    total_rounds = test_minutes * rounds_per_minute

    for i in range(total_rounds):
        response = await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])
        assert response.strip(), f"第 {i+1} 轮回复为空"

    # 验证 LLM 调用次数
    assert mock_llm.call_count == total_rounds, \
        f"Expected {total_rounds} LLM calls, got {mock_llm.call_count}"


@pytest.mark.asyncio
async def test_stability_alternating_proactive_and_chat(stability_runtime):
    """主动和对话交替执行稳定性。"""
    runtime, mock_llm, _ = stability_runtime

    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 95

    for i in range(5):
        # proactive tick
        runtime.initiative_engine.reset_cooldown()
        runtime.initiative_engine._last_trigger_time = None
        await runtime.proactive_tick()

        # chat
        await runtime.chat(TEST_MESSAGES[i % len(TEST_MESSAGES)])

    # 所有调用应该成功（proactive 可能被抑制，实际 LLM 调用数可能少于 10）
    assert mock_llm.call_count >= 5  # 至少 5 次 chat 调用
