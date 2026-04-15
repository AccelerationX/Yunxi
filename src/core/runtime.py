"""云汐 3.0 运行时统筹层（Phase 4 感知-情感深度集成版）。

整合 ExecutionEngine、PromptBuilder、HeartLake、Perception、Memory、InitiativeEngine，
提供统一的 `chat()` 入口和 `proactive_tick()` 主动触发入口。
"""

import logging
import time
from typing import Any, Optional

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import HeartLakeUpdater
from core.cognition.initiative_engine import InitiativeEngine
from core.execution.engine import YunxiExecutionEngine
from core.initiative.continuity import CompanionContinuityService
from core.initiative.event_system import ThreeLayerInitiativeEventSystem
from core.mcp.hub import MCPHub
from core.prompt_builder import RuntimeContext, YunxiPromptBuilder
from domains.memory.manager import MemoryManager
from domains.perception.coordinator import PerceptionCoordinator


logger = logging.getLogger(__name__)


class YunxiRuntime:
    """云汐运行时。

    职责：
    - 每次收到用户输入时，从各子系统采集快照并更新感知-情感状态
    - 构建 system prompt
    - 调用 ExecutionEngine 完成对话流转
    - 支持无用户输入时的主动触发
    """

    def __init__(
        self,
        engine: YunxiExecutionEngine,
        prompt_builder: YunxiPromptBuilder,
        heart_lake: HeartLake,
        perception: PerceptionCoordinator,
        memory: MemoryManager,
        continuity: Optional[CompanionContinuityService] = None,
        initiative_event_system: Optional[ThreeLayerInitiativeEventSystem] = None,
        heart_lake_updater: Optional[HeartLakeUpdater] = None,
        initiative_engine: Optional[InitiativeEngine] = None,
        mcp_hub: Optional[MCPHub] = None,
    ):
        self.engine = engine
        self.prompt_builder = prompt_builder
        self.heart_lake = heart_lake
        self.perception = perception
        self.memory = memory
        self.continuity = continuity or CompanionContinuityService()
        self.initiative_event_system = initiative_event_system
        self.heart_lake_updater = heart_lake_updater or HeartLakeUpdater(heart_lake)
        self.initiative_engine = initiative_engine or InitiativeEngine()
        self.mcp_hub = mcp_hub
        self._last_tick_time: float = time.time()
        if self.mcp_hub is not None and self.mcp_hub.audit.memory_manager is None:
            self.mcp_hub.audit.memory_manager = self.memory

    async def chat(self, user_input: str) -> str:
        """接收用户输入，返回云汐的回复。"""
        self.heart_lake_updater.on_user_input(user_input)
        self._tick_perception_and_emotion()
        context = self.get_context()
        system_prompt = self.prompt_builder.build_system_prompt(context)
        result = await self.engine.respond(
            user_input=user_input,
            system_prompt=system_prompt,
            runtime_context=context,
        )
        self.continuity.record_exchange(
            user_message=user_input,
            assistant_message=result.content,
            proactive=False,
        )
        if result.content:
            self.heart_lake_updater.on_interaction_completed()
        return result.content

    async def proactive_tick(self) -> Optional[str]:
        """无用户输入时的主动心跳，若触发主动对话则返回内容。"""
        events = self._tick_perception_and_emotion()
        decision = self.initiative_engine.evaluate(
            heart_lake=self.heart_lake,
            events=events,
            current_time=time.time(),
            unanswered_proactive_count=self.continuity.unanswered_proactive_count,
        )

        if not decision.trigger:
            return None

        context = self.get_context()
        event_context = self._select_initiative_event_context()
        context.initiative_context = self._build_initiative_context(
            decision_reason=decision.reason,
            event_context=event_context,
        )
        system_prompt = self.prompt_builder.build_proactive_prompt(context)

        # 主动触发使用空用户输入，由 system prompt 驱动生成
        result = await self.engine.respond(
            user_input="",
            system_prompt=system_prompt,
            runtime_context=context,
        )

        if result.content:
            self.continuity.record_assistant_message(
                result.content,
                proactive=True,
            )

        return result.content

    def _select_initiative_event_context(self) -> str:
        """Select one life event as LLM context for proactive generation."""
        if self.initiative_event_system is None:
            return ""
        event = self.initiative_event_system.select_event()
        return self.initiative_event_system.build_prompt_context(event)

    def _build_initiative_context(self, decision_reason: str, event_context: str) -> str:
        """Combine trigger reason and life-event material without script output."""
        if not event_context:
            return decision_reason
        return (
            f"{decision_reason}\n\n"
            "life_event_material:\n"
            f"{event_context}"
        )

    def _tick_perception_and_emotion(self) -> list:
        """刷新感知并更新情感状态，返回感知事件列表。"""
        now = time.time()
        elapsed = max(0.0, now - self._last_tick_time)
        self._last_tick_time = now

        events = self.perception.update()
        snapshot = self.perception.get_snapshot()
        self.heart_lake_updater.on_perception_tick(
            snapshot=snapshot,
            events=events,
            elapsed_seconds=elapsed,
        )
        return events

    def get_context(self) -> RuntimeContext:
        """从各子系统构建运行时上下文快照。"""
        perception_snapshot = self.perception.get_snapshot()
        memory_summary = self.memory.get_memory_summary(
            limit=self.prompt_builder.config.max_memory_lines
        )
        failure_hints = self.memory.get_failure_hints()

        available_tools: list[str] = []
        if self.mcp_hub is not None:
            try:
                available_tools = self.mcp_hub.list_available_tool_names()
            except RuntimeError as exc:
                logger.warning("Failed to read available MCP tools: %s", exc)

        continuity_summary = self.continuity.get_summary()

        return RuntimeContext(
            mode="daily_mode",
            heart_lake_state=self.heart_lake,
            perception_snapshot=perception_snapshot,
            memory_summary=memory_summary,
            failure_hints=failure_hints,
            continuity_summary=continuity_summary,
            available_tools=available_tools,
            factory_status=None,
        )

    def reset(self) -> None:
        """重置运行时状态。"""
        self.engine.reset_context()
        self._last_tick_time = time.time()
        if self.initiative_engine:
            self.initiative_engine.reset_cooldown()
        self.continuity.reset()
