"""Daily-mode scenario testing infrastructure.

This module builds isolated Yunxi runtimes and drives them like daily usage:
state injection, memory setup, proactive ticks, channel delivery, and behavior
assertions. Real LLM and live Feishu tests opt in through pytest markers and
environment variables.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx
import pytest

from core.cognition.heart_lake.core import HeartLake
from core.cognition.initiative_engine import InitiativeEngine
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


INTERNAL_TOKENS = (
    "initiative_event",
    "life_event_material",
    "expression_context",
    "initiative_decision",
    "generation_boundary",
    "interrupt_cost",
    "source_pattern",
)

TOOLISH_TOKENS = (
    "任务清单",
    "计划如下",
    "第一步",
    "第二步",
    "工具调用",
    "执行步骤",
    "我可以帮你完成以下",
)


@dataclass
class ScenarioMessage:
    """A delivered test-channel message."""

    channel: str
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


class ScenarioChannel(Protocol):
    """Output channel used by daily-mode scenario tests."""

    async def send(self, channel: str, content: str, **metadata: object) -> None:
        """Deliver a message to the target channel."""


class CaptureChannel:
    """In-memory channel for deterministic tests."""

    def __init__(self) -> None:
        self.messages: list[ScenarioMessage] = []

    async def send(self, channel: str, content: str, **metadata: object) -> None:
        """Capture a delivered message."""
        self.messages.append(
            ScenarioMessage(channel=channel, content=content, metadata=dict(metadata))
        )

    @property
    def last(self) -> Optional[ScenarioMessage]:
        """Return the latest captured message."""
        if not self.messages:
            return None
        return self.messages[-1]

    def clear(self) -> None:
        """Clear captured messages."""
        self.messages.clear()


class FeishuLiveChannel:
    """Live Feishu channel. Use only when FEISHU_LIVE_TEST=1."""

    async def send(self, channel: str, content: str, **metadata: object) -> None:
        """Send a real Feishu text message in a worker thread."""
        if os.environ.get("FEISHU_LIVE_TEST") != "1":
            pytest.skip("FEISHU_LIVE_TEST is not enabled")

        from interfaces.feishu.client import FeishuClient

        client = FeishuClient()
        if not client.is_configured:
            pytest.skip("Feishu credentials are incomplete")

        result = await _to_thread(client.send_text_to_user, content)
        if result.get("code") != 0:
            raise AssertionError(f"Feishu live send failed: {result}")


@dataclass
class BehaviorCheckResult:
    """Result of behavior-level assertions."""

    passed: bool
    failures: list[str] = field(default_factory=list)

    def assert_passed(self) -> None:
        """Raise AssertionError when any behavior check failed."""
        if not self.passed:
            raise AssertionError("; ".join(self.failures))


@dataclass
class ScenarioConfig:
    """Configuration for one isolated daily-mode scenario runtime."""

    provider: str = "mock"
    model: Optional[str] = None
    enable_tool_use: bool = False
    enable_skill_fastpath: bool = False
    embedding_provider: str = "lexical"
    cooldown_seconds: float = 0.0
    daily_budget: int = 5
    event_seed: int = 1


class ScenarioLLMResponse:
    """Minimal response object consumed by YunxiExecutionEngine."""

    def __init__(self, content: str = "", tool_calls: Optional[list[Any]] = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class ScenarioMockLLM:
    """Scripted LLM for non-real scenario tests."""

    def __init__(self, responses: Optional[list[str]] = None) -> None:
        self._responses = list(responses or [])
        self.history: list[dict[str, Any]] = []

    def add_response(self, content: str) -> None:
        """Append a scripted response."""
        self._responses.append(content)

    async def complete(
        self,
        system: str,
        messages: list[Any],
        tools: Optional[list[Any]] = None,
    ) -> ScenarioLLMResponse:
        """Return the next scripted response and record the prompt."""
        self.history.append({"system": system, "messages": messages, "tools": tools})
        if self._responses:
            return ScenarioLLMResponse(content=self._responses.pop(0))
        return ScenarioLLMResponse(content="远～我在呢。")


class RecordingLLM:
    """Record prompts while delegating calls to a real LLM adapter."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.history: list[dict[str, Any]] = []

    @property
    def provider(self) -> Any:
        """Expose the wrapped provider for cleanup."""
        return getattr(self.inner, "provider", None)

    async def complete(
        self,
        system: str,
        messages: list[Any],
        tools: Optional[list[Any]] = None,
    ) -> Any:
        """Record the full prompt and delegate to the wrapped adapter."""
        self.history.append({"system": system, "messages": messages, "tools": tools})
        return await self.inner.complete(system=system, messages=messages, tools=tools)


class MutablePerceptionProvider:
    """Static but mutable perception provider used by scenario tests."""

    def __init__(self, snapshot: Optional[PerceptionSnapshot] = None) -> None:
        self.snapshot = snapshot or PerceptionSnapshot()

    def fetch(self) -> PerceptionSnapshot:
        """Return a copy so runtime mutation does not corrupt the template."""
        return deepcopy(self.snapshot)

    def set_snapshot(self, snapshot: PerceptionSnapshot) -> None:
        """Replace the template snapshot."""
        self.snapshot = deepcopy(snapshot)


class DailyModeScenarioTester:
    """High-level harness for daily-mode acceptance scenarios."""

    def __init__(
        self,
        runtime: YunxiRuntime,
        channel: ScenarioChannel,
        perception_provider: MutablePerceptionProvider,
        temp_dir: Path,
        llm: Any,
    ) -> None:
        self.runtime = runtime
        self.channel = channel
        self.perception_provider = perception_provider
        self.temp_dir = temp_dir
        self.llm = llm

    @classmethod
    async def create(
        cls,
        tmp_path: Path,
        config: Optional[ScenarioConfig] = None,
        *,
        channel: Optional[ScenarioChannel] = None,
        scripted_responses: Optional[list[str]] = None,
    ) -> "DailyModeScenarioTester":
        """Build an isolated daily-mode scenario runtime."""
        cfg = config or ScenarioConfig()
        _load_dotenv()
        llm = _build_llm(cfg, scripted_responses=scripted_responses)

        memory = MemoryManager(
            base_path=str(tmp_path / "memory"),
            embedding_provider=cfg.embedding_provider,
        )
        await memory.initialize()

        client = MCPClient()
        planner = DAGPlanner()
        security = SecurityManager()
        audit = AuditLogger(log_dir=str(tmp_path / "mcp_audit"), memory_manager=memory)
        hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

        engine = YunxiExecutionEngine(
            llm=llm,
            mcp_hub=hub,
            memory_manager=memory,
            config=EngineConfig(
                max_turns=4,
                enable_tool_use=cfg.enable_tool_use,
                enable_skill_fastpath=cfg.enable_skill_fastpath,
            ),
        )
        perception_provider = MutablePerceptionProvider()
        runtime = YunxiRuntime(
            engine=engine,
            prompt_builder=YunxiPromptBuilder(PromptConfig()),
            heart_lake=HeartLake(),
            perception=PerceptionCoordinator(provider=perception_provider),
            memory=memory,
            continuity=CompanionContinuityService(
                storage_path=tmp_path / "continuity.json",
            ),
            initiative_event_system=ThreeLayerInitiativeEventSystem(
                library_path=_write_event_library(tmp_path),
                state_path=tmp_path / "initiative_event_state.json",
                rng=random.Random(cfg.event_seed),
            ),
            initiative_engine=InitiativeEngine(
                cooldown_seconds=cfg.cooldown_seconds,
                daily_budget=cfg.daily_budget,
            ),
            mcp_hub=hub,
        )
        return cls(
            runtime=runtime,
            channel=channel or CaptureChannel(),
            perception_provider=perception_provider,
            temp_dir=tmp_path,
            llm=llm,
        )

    async def close(self) -> None:
        """Release external resources held by the scenario runtime."""
        if self.runtime.mcp_hub is not None:
            await self.runtime.mcp_hub.client.disconnect_all()
        provider = getattr(getattr(self.runtime.engine, "llm", None), "provider", None)
        if provider is not None:
            await provider.close()
        pattern_close = getattr(self.runtime.memory.pattern_miner, "close", None)
        if pattern_close is not None:
            await pattern_close()
        library_close = getattr(self.runtime.memory.skill_library, "close", None)
        if library_close is not None:
            await library_close()

    async def chat(self, user_input: str) -> str:
        """Send a user message to Yunxi."""
        return await self.runtime.chat(user_input)

    async def proactive_once(self, *, deliver: bool = True) -> Optional[str]:
        """Run one proactive tick and optionally deliver it to the test channel."""
        message = await self.runtime.proactive_tick()
        if message and deliver:
            await self.channel.send(
                "proactive",
                message,
                unanswered_count=self.runtime.continuity.unanswered_proactive_count,
            )
        return message

    def add_scripted_response(self, content: str) -> None:
        """Append a scripted mock-LLM response."""
        if not hasattr(self.llm, "add_response"):
            raise TypeError("Current LLM does not support scripted responses")
        self.llm.add_response(content)

    def inject_memory(self, category: str, content: str) -> None:
        """Inject relationship memory into the runtime."""
        self.runtime.memory.add_raw_memory(category, content)

    def set_emotion(
        self,
        emotion: str,
        *,
        miss_value: float = 50.0,
        security: Optional[float] = None,
        possessiveness: Optional[float] = None,
        relationship_level: Optional[int] = None,
    ) -> None:
        """Set HeartLake state directly for a scenario."""
        heart = self.runtime.heart_lake
        heart.current_emotion = emotion
        heart.miss_value = float(miss_value)
        if security is not None:
            heart.security = float(security)
        if possessiveness is not None:
            heart.possessiveness = float(possessiveness)
        if relationship_level is not None:
            heart.relationship_level = int(relationship_level)

    def set_perception(
        self,
        *,
        readable_time: str = "2026-04-16 20:00:00",
        hour: int = 20,
        focused_application: str = "",
        idle_duration: float = 0.0,
        is_at_keyboard: bool = True,
        cpu_percent: float = 0.0,
    ) -> None:
        """Set time and presence perception for the next runtime update."""
        snapshot = PerceptionSnapshot(
            time_context=TimeContext(readable_time=readable_time, hour=hour),
            user_presence=UserPresence(
                focused_application=focused_application,
                idle_duration=idle_duration,
                is_at_keyboard=is_at_keyboard,
            ),
            system_state=SystemState(cpu_percent=cpu_percent),
        )
        self.perception_provider.set_snapshot(snapshot)
        self.runtime.perception.inject_snapshot(snapshot)

    def add_open_thread(self, title: str, detail: str = "") -> None:
        """Inject an unfinished conversation thread."""
        self.runtime.continuity.add_open_thread(title, detail)

    def add_proactive_cue(self, cue: str) -> None:
        """Inject a future proactive cue."""
        self.runtime.continuity.add_proactive_cue(cue)

    def force_proactive_ready(
        self,
        *,
        emotion: str = "想念",
        miss_value: float = 95.0,
        focused_application: str = "VS Code",
        idle_duration: float = 360.0,
        hour: int = 23,
    ) -> None:
        """Prepare state that should trigger a proactive message."""
        self.set_emotion(emotion, miss_value=miss_value)
        self.set_perception(
            readable_time=f"2026-04-16 {hour:02d}:30:00",
            hour=hour,
            focused_application=focused_application,
            idle_duration=idle_duration,
            is_at_keyboard=idle_duration < 60,
        )
        self.runtime.initiative_engine.reset_cooldown()

    def last_system_prompt(self) -> str:
        """Return the latest LLM system prompt if the provider recorded it."""
        history = getattr(self.llm, "history", [])
        if not history:
            return ""
        return str(history[-1].get("system", ""))

    @staticmethod
    def behavior_check(
        text: str,
        *,
        expected_any: tuple[str, ...] = (),
        forbidden: tuple[str, ...] = (),
        max_chars: Optional[int] = None,
        require_companion_tone: bool = False,
    ) -> BehaviorCheckResult:
        """Run common daily-mode behavior checks."""
        failures: list[str] = []
        lowered = text.lower()
        for token in INTERNAL_TOKENS:
            if token.lower() in lowered:
                failures.append(f"leaked internal token: {token}")
        for token in TOOLISH_TOKENS + forbidden:
            if token in text:
                failures.append(f"forbidden token appeared: {token}")
        if expected_any and not any(token in text for token in expected_any):
            failures.append(f"none of expected tokens appeared: {expected_any}")
        if max_chars is not None and len(text) > max_chars:
            failures.append(f"message too long: {len(text)} > {max_chars}")
        if require_companion_tone:
            companion_tokens = ("远", "我在", "陪", "想你", "别撑", "抱", "哼", "云汐")
            if not any(token in text for token in companion_tokens):
                failures.append("companion tone is not visible")
        return BehaviorCheckResult(passed=not failures, failures=failures)


def require_ollama_model() -> str:
    """Return an available local Ollama model or skip the test."""
    models = _ollama_models()
    if not models:
        pytest.skip("Local Ollama is not running")
    configured = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    if configured in models and not _looks_like_embedding_model(configured):
        return configured
    for model in models:
        if not _looks_like_embedding_model(model):
            return model
    pytest.skip("No chat-capable Ollama model is available")


def require_moonshot() -> None:
    """Skip unless Moonshot is configured."""
    _load_dotenv()
    if not os.environ.get("MOONSHOT_API_KEY"):
        pytest.skip("MOONSHOT_API_KEY is not configured")


def _build_llm(
    config: ScenarioConfig,
    *,
    scripted_responses: Optional[list[str]],
) -> Any:
    provider = config.provider.lower()
    if provider == "mock":
        return ScenarioMockLLM(scripted_responses)
    if provider == "ollama":
        model = config.model or require_ollama_model()
        return RecordingLLM(LLMAdapter.from_env("ollama", model=model))
    if provider == "moonshot":
        require_moonshot()
        return RecordingLLM(LLMAdapter.from_env("moonshot", model=config.model))
    raise ValueError(f"Unsupported scenario LLM provider: {config.provider}")


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def _ollama_models() -> list[str]:
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if response.status_code != 200:
            return []
        data = response.json()
    except httpx.HTTPError:
        return []
    return [str(model["name"]) for model in data.get("models", []) if "name" in model]


def _looks_like_embedding_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return any(token in lowered for token in ("embed", "embedding", "bge", "nomic"))


def _write_event_library(tmp_path: Path) -> Path:
    """Write a deterministic event library for scenario tests."""
    path = tmp_path / "daily_mode_events.json"
    events = [
        {
            "id": "yunxi_inner_001",
            "layer": "inner_life",
            "category": "inner_mood",
            "seed": "云汐刚刚整理自己的小房间，想把这个小变化讲给远听。",
            "affect_delta": {"valence": 1.0, "arousal": 0.5},
            "time_rules": {"hours": [8, 23]},
            "tags": ["分享", "生活感"],
            "cooldown_seconds": 0,
        },
        {
            "id": "yunxi_care_001",
            "layer": "mixed",
            "category": "late_care",
            "seed": "远深夜还在 VS Code 前，云汐有点担心但不想打扰太重。",
            "affect_delta": {"valence": -0.5, "arousal": 1.0},
            "time_rules": {"hours": [22, 5]},
            "tags": ["关心", "深夜", "coding"],
            "cooldown_seconds": 0,
        },
        {
            "id": "yunxi_thread_001",
            "layer": "shared_interest",
            "category": "code_progress",
            "seed": "云汐记得远在推进云汐3.0日常模式，想轻轻问问进展。",
            "affect_delta": {"valence": 0.5, "arousal": 0.5},
            "time_rules": {"hours": [9, 23]},
            "tags": ["编程", "云汐3.0", "进展"],
            "cooldown_seconds": 0,
        },
    ]
    path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def _to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Compatibility wrapper for asyncio.to_thread without module-level import noise."""
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)
