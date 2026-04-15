"""对话验证框架。

以"直接传入指令、观察真实回复"的方式验证云汐的整体行为。
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest_asyncio

from core.cognition.heart_lake.core import HeartLake
from core.execution.engine import EngineConfig, YunxiExecutionEngine
from core.mcp.client import MCPClient
from core.mcp.hub import MCPHub
from core.mcp.planner import DAGPlanner
from core.mcp.security import SecurityManager
from core.mcp.audit_logger import AuditLogger
from core.prompt_builder import PromptConfig, YunxiPromptBuilder
from core.runtime import YunxiRuntime
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator, PerceptionSnapshot


@dataclass
class Turn:
    """对话剧本中的单轮"""
    user: str
    expected_keywords: List[str] = field(default_factory=list)
    forbidden_keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class TestResult:
    """单轮测试结果"""
    turn_index: int
    user_input: str
    assistant_response: str
    passed: bool
    reason: Optional[str] = None


class MockLLM:
    """测试用的 mock LLM。

    根据预设规则返回回复，用于在没有真实 LLM  provider 时验证 Engine 流程。
    """

    def __init__(self, responses: Optional[List[Any]] = None):
        self._responses = responses or []
        self._call_index = 0
        self.history: List[Dict[str, Any]] = []

    def add_response(self, content: str, tool_calls: Optional[List[Any]] = None) -> None:
        """添加一条预设回复。"""
        self._responses.append(MockLLMResponse(content=content, tool_calls=tool_calls))

    async def complete(self, system: str, messages: List[Any], tools: Optional[List[Any]] = None) -> "MockLLMResponse":
        self.history.append({"system": system, "messages": messages, "tools": tools})
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        return MockLLMResponse(content="（mock 默认回复）")


class MockLLMResponse:
    """MockLLM 的返回值对象。"""

    def __init__(self, content: str = "", tool_calls: Optional[List[Any]] = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockPerceptionProvider:
    """Static perception provider for conversation tests."""

    def fetch(self) -> PerceptionSnapshot:
        return PerceptionSnapshot()


class YunxiConversationTester:
    """对话验证框架核心类。"""

    def __init__(self):
        self.runtime = self._build_test_runtime()

    def _build_test_runtime(self) -> YunxiRuntime:
        """构建一个用于测试的运行时实例。"""
        prompt_builder = YunxiPromptBuilder(PromptConfig())

        # 构造最小 MCPHub（不连接真实 server，仅用于接口存在）
        client = MCPClient()
        planner = DAGPlanner()
        security = SecurityManager()
        audit = AuditLogger(log_dir="logs/mcp_audit_test")
        mcp_hub = MCPHub(
            client=client,
            planner=planner,
            security=security,
            audit=audit,
        )

        # Mock LLM：测试用例自行填充回复
        mock_llm = MockLLM()

        memory = MemoryManager(base_path="tests/integration/temp_memory")
        engine = YunxiExecutionEngine(
            llm=mock_llm,
            mcp_hub=mcp_hub,
            memory_manager=memory,
            config=EngineConfig(enable_tool_use=False, enable_skill_fastpath=False),
        )
        heart_lake = HeartLake()
        perception = PerceptionCoordinator(provider=MockPerceptionProvider())

        return YunxiRuntime(
            engine=engine,
            prompt_builder=prompt_builder,
            heart_lake=heart_lake,
            perception=perception,
            memory=memory,
            mcp_hub=mcp_hub,
        )

    async def talk(self, text: str) -> str:
        """直接发送消息给云汐，返回她的回复。"""
        return await self.runtime.chat(text)

    def inject_memory(self, category: str, content: str) -> None:
        """向记忆系统注入测试数据。"""
        if category == "preference":
            self.runtime.memory.record_preference(content)
        elif category == "episode":
            self.runtime.memory.record_episode(content)
        elif category == "promise":
            self.runtime.memory.record_promise(content)
        else:
            self.runtime.memory.add_raw_memory(category, content)

    def set_heart_lake(self, emotion: str, miss_value: int = 50, **kwargs: Any) -> None:
        """设置情感状态。"""
        hl = self.runtime.heart_lake
        hl.current_emotion = emotion
        hl.miss_value = float(miss_value)
        for k, v in kwargs.items():
            setattr(hl, k, v)

    def set_perception(self, **kwargs: Any) -> None:
        """设置感知状态。"""
        p = self.runtime.perception
        snapshot = deepcopy(p.get_snapshot())
        for k, v in kwargs.items():
            setattr(snapshot, k, v)
        for k, v in kwargs.items():
            if hasattr(p, k):
                setattr(p, k, v)
        if isinstance(snapshot, PerceptionSnapshot):
            p.inject_snapshot(snapshot)

    def set_continuity(self, **kwargs: Any) -> None:
        """设置连续性状态（Stub）。"""
        if self.runtime.continuity and hasattr(self.runtime.continuity, "_state"):
            for k, v in kwargs.items():
                setattr(self.runtime.continuity._state, k, v)

    def reset(self) -> None:
        """重置运行时状态。"""
        self.runtime.reset()
        # 清空测试记忆
        self.runtime.memory._preferences.clear()
        self.runtime.memory._episodes.clear()
        self.runtime.memory._promises.clear()
        self.runtime.memory.failure_replay.clear()
        # 重置 mock LLM
        self.runtime.engine.llm._responses.clear()
        self.runtime.engine.llm._call_index = 0
        self.runtime.engine.llm.history.clear()

    async def run_script(self, turns: List[Turn]) -> List[TestResult]:
        """执行一个多轮对话剧本，并自动断言。"""
        results: List[TestResult] = []
        for i, turn in enumerate(turns):
            response = await self.talk(turn.user)
            passed = True
            reasons: List[str] = []

            for kw in turn.expected_keywords:
                if kw not in response:
                    passed = False
                    reasons.append(f"缺少期望关键词：'{kw}'")

            for kw in turn.forbidden_keywords:
                if kw in response:
                    passed = False
                    reasons.append(f"出现了禁用关键词：'{kw}'")

            results.append(
                TestResult(
                    turn_index=i,
                    user_input=turn.user,
                    assistant_response=response,
                    passed=passed,
                    reason="; ".join(reasons) if reasons else None,
                )
            )

        return results
