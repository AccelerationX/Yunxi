"""验证脚本通用框架 — 创建隔离的 YunxiRuntime 并记录状态。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.cognition.heart_lake.core import HeartLake
from core.cognition.initiative_engine.engine import InitiativeEngine
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.llm.adapter import LLMAdapter
from core.mcp.client import MCPClient
from core.mcp.hub import MCPHub
from core.mcp.planner import DAGPlanner
from core.mcp.security import SecurityManager
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.runtime import YunxiRuntime
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator, PerceptionSnapshot


class MutablePerceptionProvider:
    """Static but mutable perception provider used by tests."""

    def __init__(self, snapshot: Optional[PerceptionSnapshot] = None) -> None:
        self.snapshot = snapshot or PerceptionSnapshot()

    def get_snapshot(self) -> PerceptionSnapshot:
        return self.snapshot

    def set_snapshot(self, snapshot: PerceptionSnapshot) -> None:
        self.snapshot = snapshot

    def fetch(self) -> PerceptionSnapshot:
        """Compatible with PerceptionCoordinator's provider interface."""
        return self.snapshot


@dataclass
class TurnRecord:
    """单轮对话记录。"""
    turn: int
    user_input: str
    assistant_response: str = ""
    heart_lake_snapshot: Dict[str, Any] = field(default_factory=dict)
    semantic_appraisal_used: bool = False
    prompt_preview: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """验证结果。"""
    test_name: str
    passed: bool = False
    turns: List[TurnRecord] = field(default_factory=list)
    summary: str = ""
    errors: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


class ScriptLLM:
    """脚本化 LLM：按顺序返回预设响应，无需真实 API 调用。

    用于快速验证代码路径和情绪流转逻辑，不消耗 API 额度。
    """

    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = list(responses or [])
        self._index = 0
        self.call_count = 0

    def add_response(self, text: str) -> None:
        self._responses.append(text)

    async def complete(self, system: str, messages: List[Any], tools: Optional[List[Any]] = None):
        from core.llm.adapter import _AdapterResponse

        self.call_count += 1
        if self._index < len(self._responses):
            text = self._responses[self._index]
            self._index += 1
            return _AdapterResponse(content=text)
        # 默认兜底响应
        return _AdapterResponse(content="嗯嗯，云汐知道了～")


def _load_dotenv() -> None:
    """Load .env if present."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _build_llm(scripted: Optional[List[str]] = None):
    """Build LLM adapter: scripted mode or real mode."""
    if scripted is not None:
        return ScriptLLM(scripted)
    # Real LLM mode
    _load_dotenv()
    provider = os.environ.get("YUNXI_VALIDATION_PROVIDER", "moonshot")
    model = os.environ.get("YUNXI_VALIDATION_MODEL")
    return LLMAdapter.from_env(provider=provider, model=model)


async def build_isolated_runtime(
    tmp_path: Path,
    *,
    scripted_responses: Optional[List[str]] = None,
    prompt_config: Optional[PromptConfig] = None,
) -> YunxiRuntime:
    """创建一个完全隔离的 YunxiRuntime，用于验证。"""
    llm = _build_llm(scripted_responses)

    memory = MemoryManager(
        base_path=str(tmp_path / "memory"),
        embedding_provider="mock",
    )
    await memory.initialize()

    client = MCPClient()
    planner = DAGPlanner()
    security = SecurityManager()
    audit = type("Audit", (), {"memory_manager": memory})()
    hub = MCPHub(client=client, planner=planner, security=security, audit=audit)

    engine = YunxiExecutionEngine(
        llm=llm,
        mcp_hub=hub,
        memory_manager=memory,
        config=EngineConfig(max_turns=4, enable_tool_use=False),
    )

    hl = HeartLake()
    # 注入测试友好的初始状态
    hl.current_emotion = "平静"
    hl.miss_value = 10.0
    hl.security = 80.0

    runtime = YunxiRuntime(
        engine=engine,
        prompt_builder=YunxiPromptBuilder(prompt_config or PromptConfig()),
        heart_lake=hl,
        perception=PerceptionCoordinator(provider=MutablePerceptionProvider()),
        memory=memory,
        initiative_engine=InitiativeEngine(),
        mcp_hub=hub,
    )
    return runtime


def capture_heart_lake(hl: HeartLake) -> Dict[str, Any]:
    """捕获 HeartLake 关键状态。"""
    return {
        "current_emotion": hl.current_emotion,
        "compound_labels": list(hl.compound_labels),
        "last_appraisal_reason": hl.last_appraisal_reason,
        "miss_value": round(hl.miss_value, 1),
        "security": round(hl.security, 1),
        "playfulness": round(hl.playfulness, 1),
        "vulnerability": round(hl.vulnerability, 1),
        "tenderness": round(hl.tenderness, 1),
    }


async def run_chat_turn(
    runtime: YunxiRuntime,
    user_input: str,
    turn: int,
    capture_prompt: bool = False,
) -> TurnRecord:
    """运行单轮对话并记录状态。"""
    record = TurnRecord(turn=turn, user_input=user_input)

    try:
        # 获取对话前的状态
        before = capture_heart_lake(runtime.heart_lake)
        record.heart_lake_snapshot["before"] = before

        # 发送消息
        response = await runtime.chat(user_input)
        record.assistant_response = response

        # 获取对话后的状态
        after = capture_heart_lake(runtime.heart_lake)
        record.heart_lake_snapshot["after"] = after

        # 检查是否使用了语义评估（通过检测 heart_lake._last_semantic_appraisal_at）
        now = __import__("time").time()
        last_appraisal = getattr(runtime.heart_lake, "_last_semantic_appraisal_at", 0)
        record.semantic_appraisal_used = (now - last_appraisal) < 5.0

        if capture_prompt:
            # 构建一个预览用的 prompt（不实际发送）
            ctx = runtime.get_context(user_input=user_input)
            record.prompt_preview = runtime.prompt_builder.build_system_prompt(ctx)[:500]

    except Exception as e:
        record.errors.append(str(e))

    return record
