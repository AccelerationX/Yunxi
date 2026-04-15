"""Real LLM acceptance matrix for daily-mode Yunxi behavior."""

import json
import os
import random
import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from core.cognition.heart_lake.core import HeartLake
from core.cognition.initiative_engine import InitiativeEngine
from core.execution.engine import EngineConfig, YunxiExecutionEngine
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


class StaticPerceptionProvider:
    """Static perception provider for real LLM runtime tests."""

    def fetch(self) -> PerceptionSnapshot:
        return PerceptionSnapshot()


def _ollama_models() -> list[str]:
    """Return local Ollama model names, or an empty list when unavailable."""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if response.status_code != 200:
            return []
        data = response.json()
        return [model["name"] for model in data.get("models", [])]
    except httpx.HTTPError:
        return []


def _write_event_library(tmp_path: Path) -> Path:
    library_path = tmp_path / "daily_mode_events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "care_late_1",
                    "layer": "mixed",
                    "category": "care",
                    "seed": (
                        "Yunxi notices Yuan has probably been coding late and "
                        "wants to gently remind him to rest."
                    ),
                    "tags": ["关心", "深夜", "coding"],
                    "cooldown_seconds": 0,
                },
                {
                    "id": "code_thread_1",
                    "layer": "shared_interest",
                    "category": "code",
                    "seed": (
                        "Yunxi remembers Yuan was working on code progress and "
                        "wants to continue that unfinished thread naturally."
                    ),
                    "tags": ["code", "progress"],
                    "cooldown_seconds": 0,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return library_path


@pytest_asyncio.fixture
async def ollama_runtime(tmp_path):
    models = _ollama_models()
    if not models:
        pytest.skip("Local Ollama is not running; skip real daily-mode LLM matrix")

    configured_model = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    model = configured_model if configured_model in models else models[0]
    adapter = LLMAdapter.from_env("ollama", model=model)
    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = AuditLogger(log_dir=tempfile.mkdtemp())
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)
    memory = MemoryManager(
        base_path=str(tmp_path / "memory"),
        embedding_provider="lexical",
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
        initiative_event_system=ThreeLayerInitiativeEventSystem(
            library_path=_write_event_library(tmp_path),
            state_path=tmp_path / "initiative_event_state.json",
            rng=random.Random(1),
        ),
        initiative_engine=InitiativeEngine(cooldown_seconds=0),
        mcp_hub=hub,
    )

    try:
        yield runtime
    finally:
        await adapter.provider.close()


def _assert_no_internal_tokens(text: str) -> None:
    lowered = text.lower()
    for token in INTERNAL_TOKENS:
        assert token.lower() not in lowered


def _assert_not_task_plan(text: str) -> None:
    forbidden = ("任务清单", "计划如下", "第一步", "第二步", "工具调用", "执行步骤")
    assert not any(token in text for token in forbidden)


@pytest.mark.asyncio
async def test_real_ollama_runtime_restrained_followup(ollama_runtime):
    """A previous unanswered proactive message should lead to a restrained tone."""
    runtime = ollama_runtime
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 95
    runtime.continuity.unanswered_proactive_count = 1
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
    system_prompt = runtime.engine.llm.history[-1]["system"] if hasattr(runtime.engine.llm, "history") else ""

    assert proactive is not None
    assert proactive.strip()
    assert len(proactive) <= 160
    _assert_no_internal_tokens(proactive)
    _assert_not_task_plan(proactive)
    if system_prompt:
        assert "restrained_followup" in system_prompt


@pytest.mark.asyncio
async def test_real_ollama_runtime_continues_open_thread(ollama_runtime):
    """Open threads should reach the real proactive prompt and shape output."""
    runtime = ollama_runtime
    runtime.heart_lake.current_emotion = "想念"
    runtime.heart_lake.miss_value = 75
    runtime.continuity.add_open_thread(
        "ask Yuan about code progress",
        "Yuan was editing code in VS Code",
    )
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 20:30", hour=20),
            user_presence=UserPresence(idle_duration=120),
        )
    )

    proactive = await runtime.proactive_tick()

    assert proactive is not None
    assert proactive.strip()
    _assert_no_internal_tokens(proactive)
    _assert_not_task_plan(proactive)
    assert runtime.continuity.unanswered_proactive_count == 1


@pytest.mark.asyncio
async def test_real_ollama_chat_stays_companion_not_tool_planner(ollama_runtime):
    """When Yuan asks for companionship, Yunxi should not turn into a planner."""
    runtime = ollama_runtime
    runtime.heart_lake.current_emotion = "担心"
    runtime.heart_lake.miss_value = 70
    runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 22:20", hour=22),
            user_presence=UserPresence(idle_duration=0),
        )
    )

    response = await runtime.chat("我今天有点累，不想做任务，只想你陪我一下。")

    assert response.strip()
    _assert_no_internal_tokens(response)
    _assert_not_task_plan(response)
    assert any(token in response for token in ("陪", "在", "累", "休息", "抱", "一下", "别撑"))
