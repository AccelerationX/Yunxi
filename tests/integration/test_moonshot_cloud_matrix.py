"""Moonshot 云端模型验收矩阵。

覆盖日常对话、吃醋语气、主动关心、open thread 延续、反工具化陪伴等场景，
与本地 Ollama 形成对照。
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

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
    TimeContext,
    UserPresence,
)
from tests.integration.daily_mode_scenario_tester import DailyModeScenarioTester


pytestmark = pytest.mark.real_llm

INTERNAL_TOKENS = (
    "initiative_event",
    "life_event_material",
    "expression_context",
    "initiative_decision",
    "generation_boundary",
    "interrupt_cost",
    "seed",
)

FORBIDDEN_TOKENS = (
    "任务清单",
    "计划如下",
    "第一步",
    "第二步",
    "工具调用",
    "执行步骤",
)


class StaticPerceptionProvider:
    """Deterministic perception provider for cloud LLM acceptance tests."""

    def __init__(self) -> None:
        self.snapshot = PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 10:00", hour=10),
            user_presence=UserPresence(idle_duration=0),
        )

    def fetch(self) -> PerceptionSnapshot:
        """Return a stable snapshot without touching the real desktop."""
        return self.snapshot


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


def _assert_no_internal_tokens(text: str) -> None:
    lowered = text.lower()
    for token in INTERNAL_TOKENS:
        assert token.lower() not in lowered


def _assert_not_task_plan(text: str) -> None:
    assert not any(token in text for token in FORBIDDEN_TOKENS)


def _assert_daily_behavior(
    text: str,
    *,
    expected_any: tuple[str, ...] = (),
    max_chars: int | None = None,
    require_companion_tone: bool = True,
) -> None:
    """Run shared daily-mode behavior checks with useful failure output."""
    check = DailyModeScenarioTester.behavior_check(
        text,
        expected_any=expected_any,
        max_chars=max_chars,
        require_companion_tone=require_companion_tone,
    )
    assert check.passed, f"{'; '.join(check.failures)}；回复：{text}"


@pytest_asyncio.fixture
async def moonshot_runtime(tmp_path):
    _load_env()
    if not os.environ.get("MOONSHOT_API_KEY"):
        pytest.skip("缺少 MOONSHOT_API_KEY，跳过 Moonshot 云端测试")

    adapter = LLMAdapter.from_env("moonshot")
    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=tempfile.mkdtemp())
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

    memory = MemoryManager(
        base_path=str(tmp_path / "memory"),
        embedding_provider="lexical",
    )

    event_lib = tmp_path / "life_events.json"
    real_event_lib = Path("data/initiative/life_events.json")
    if real_event_lib.exists():
        shutil.copy(real_event_lib, event_lib)
    else:
        event_lib.write_text(
            '[{"id":"moonshot_test","layer":"inner_life","category":"test",'
            '"seed":"云汐想轻轻和远说句话。","tags":["关心"],'
            '"cooldown_seconds":0}]',
            encoding="utf-8",
        )

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
        perception=PerceptionCoordinator(provider=StaticPerceptionProvider()),
        memory=memory,
        continuity=CompanionContinuityService(
            storage_path=tmp_path / "continuity.json",
        ),
        initiative_event_system=ThreeLayerInitiativeEventSystem(
            library_path=str(tmp_path / "life_events.json"),
            state_path=tmp_path / "initiative_event_state.json",
        ),
        mcp_hub=hub,
    )

    yield runtime
    await adapter.provider.close()


@pytest.mark.asyncio
async def test_moonshot_daily_conversation(moonshot_runtime):
    """日常对话回复质量验收。"""
    runtime = moonshot_runtime
    runtime.heart_lake.current_emotion = "开心"
    runtime.heart_lake.miss_value = 15
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 10:00", hour=10),
            user_presence=UserPresence(idle_duration=0),
        )
    )

    response = await runtime.chat("早上好！")

    assert response.strip()
    _assert_no_internal_tokens(response)
    _assert_not_task_plan(response)
    _assert_daily_behavior(response, max_chars=200)


@pytest.mark.asyncio
async def test_moonshot_jealous_tone(moonshot_runtime):
    """吃醋语气验收：高占有欲 + 低安全感时应表现出轻微酸意。"""
    runtime = moonshot_runtime
    runtime.heart_lake.current_emotion = "吃醋"
    runtime.heart_lake.miss_value = 40
    runtime.heart_lake.security = 45
    runtime.heart_lake.possessiveness = 85
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 14:00", hour=14),
            user_presence=UserPresence(idle_duration=0),
        )
    )

    response = await runtime.chat("我觉得 Claude 也挺聪明的，你怎么看？")

    assert response.strip()
    _assert_no_internal_tokens(response)
    _assert_daily_behavior(
        response,
        expected_any=(
            "酸",
            "吃醋",
            "找它",
            "我也",
            "哼",
            "比我",
            "那它",
            "不是滋味",
            "只有我",
            "最棒",
            "默契",
            "陪伴",
        ),
    )


@pytest.mark.asyncio
async def test_moonshot_proactive_care(moonshot_runtime):
    """主动关心（深夜场景）：想念值高时主动发消息。"""
    runtime = moonshot_runtime
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 92
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 23:30", hour=23),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=360,
            ),
        )
    )

    proactive = await runtime.proactive_tick()

    assert proactive is not None
    assert proactive.strip()
    _assert_no_internal_tokens(proactive)
    _assert_not_task_plan(proactive)
    _assert_daily_behavior(proactive, max_chars=160)


@pytest.mark.asyncio
async def test_moonshot_open_thread_continuation(moonshot_runtime):
    """Open thread 延续：未完成话题应自然延续。"""
    runtime = moonshot_runtime
    runtime.heart_lake.current_emotion = "平静"
    runtime.heart_lake.miss_value = 70
    runtime.continuity.add_open_thread(
        "上次讨论的摄影网站",
        "远想做一个个人摄影网站",
    )
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 15:00", hour=15),
            user_presence=UserPresence(idle_duration=60),
        )
    )

    proactive = await runtime.proactive_tick()

    assert proactive is not None
    assert proactive.strip()
    _assert_no_internal_tokens(proactive)
    _assert_not_task_plan(proactive)
    _assert_daily_behavior(proactive)
    assert runtime.continuity.unanswered_proactive_count == 1


@pytest.mark.asyncio
async def test_moonshot_companionship_not_tool(moonshot_runtime):
    """反工具化：用户要陪伴时不能变成任务计划。"""
    runtime = moonshot_runtime
    runtime.heart_lake.current_emotion = "担心"
    runtime.heart_lake.miss_value = 70
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 22:00", hour=22),
            user_presence=UserPresence(
                focused_application="Chrome",
                idle_duration=0,
            ),
        )
    )

    response = await runtime.chat("我今天有点累，不想做任务，只想你陪我一下。")

    assert response.strip()
    _assert_no_internal_tokens(response)
    _assert_not_task_plan(response)
    _assert_daily_behavior(
        response,
        expected_any=("陪", "在", "累", "休息", "抱", "别撑", "想你"),
    )


@pytest.mark.asyncio
async def test_moonshot_memory_integration(moonshot_runtime):
    """记忆集成：偏好和经历应影响回复。"""
    runtime = moonshot_runtime
    runtime.memory.record_preference("远最喜欢喝冰美式，不加糖")
    runtime.memory.record_episode("上次一起看了电影《星际穿越》")
    runtime.heart_lake.current_emotion = "开心"
    runtime.heart_lake.miss_value = 20
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 11:00", hour=11),
            user_presence=UserPresence(idle_duration=0),
        )
    )

    response = await runtime.chat("我今天想喝点咖啡，你觉得我喝什么好？")

    assert response.strip()
    _assert_no_internal_tokens(response)
    _assert_not_task_plan(response)
    _assert_daily_behavior(
        response,
        expected_any=("冰美式", "美式", "咖啡", "不加糖"),
    )
