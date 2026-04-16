"""云汐 3.0 运行时统筹层（Phase 4 感知-情感深度集成版）。

整合 ExecutionEngine、PromptBuilder、HeartLake、Perception、Memory、InitiativeEngine，
提供统一的 `chat()` 入口和 `proactive_tick()` 主动触发入口。
"""

import asyncio
import logging
import time
from typing import Any, Optional

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import HeartLakeUpdater
from core.cognition.initiative_engine import InitiativeDecision, InitiativeEngine
from core.execution.engine import YunxiExecutionEngine
from core.initiative.continuity import CompanionContinuityService
from core.initiative.event_system import InitiativeEventLayer, ThreeLayerInitiativeEventSystem
from core.initiative.expression_context import ExpressionContextBuilder
from core.initiative.generator import ProactiveGenerationContextBuilder
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
        expression_context_builder: Optional[ExpressionContextBuilder] = None,
        generation_context_builder: Optional[ProactiveGenerationContextBuilder] = None,
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
        self.expression_context_builder = expression_context_builder or ExpressionContextBuilder()
        self.generation_context_builder = generation_context_builder or ProactiveGenerationContextBuilder()
        self.heart_lake_updater = heart_lake_updater or HeartLakeUpdater(heart_lake)
        self.initiative_engine = initiative_engine or InitiativeEngine()
        self.mcp_hub = mcp_hub
        self._last_tick_time: float = time.time()
        self._entry_lock = asyncio.Lock()
        if self.mcp_hub is not None and self.mcp_hub.audit.memory_manager is None:
            self.mcp_hub.audit.memory_manager = self.memory

    async def chat(self, user_input: str) -> str:
        """接收用户输入，返回云汐的回复。"""
        async with self._entry_lock:
            return await self._chat_unlocked(user_input)

    async def _chat_unlocked(self, user_input: str) -> str:
        """Run one chat turn while the runtime entry lock is held."""
        self.heart_lake_updater.on_user_input(user_input)
        self._tick_perception_and_emotion()
        context = self.get_context(user_input=user_input)
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
        async with self._entry_lock:
            return await self._proactive_tick_unlocked()

    async def _proactive_tick_unlocked(self) -> Optional[str]:
        """Run one proactive tick while the runtime entry lock is held."""
        events = self._tick_perception_and_emotion()
        decision = self.initiative_engine.evaluate(
            heart_lake=self.heart_lake,
            events=events,
            current_time=time.time(),
            unanswered_proactive_count=self.continuity.unanswered_proactive_count,
            perception_snapshot=self.perception.get_snapshot(),
            continuity=self.continuity,
        )

        if not decision.trigger:
            return None

        context = self.get_context()
        event_context = self._select_initiative_event_context(decision)
        expression_context = self.expression_context_builder.build(
            decision=decision,
            heart_lake=self.heart_lake,
            continuity=self.continuity,
            perception_snapshot=context.perception_snapshot,
        ).to_prompt_context()
        context.initiative_context = self.generation_context_builder.build(
            decision=decision,
            event_context=event_context,
            expression_context=expression_context,
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

    def _select_initiative_event_context(self, decision: InitiativeDecision) -> str:
        """Select one life event as LLM context for proactive generation."""
        if self.initiative_event_system is None or not decision.should_select_event:
            return ""
        preferred_layers = self._event_layers_from_decision(decision)
        event = self.initiative_event_system.select_event(
            preferred_layers=preferred_layers,
            required_tags=decision.required_event_tags,
        )
        if event is None and decision.required_event_tags:
            event = self.initiative_event_system.select_event(
                preferred_layers=preferred_layers,
            )
        return self.initiative_event_system.build_prompt_context(event)

    def _event_layers_from_decision(
        self,
        decision: InitiativeDecision,
    ) -> list[InitiativeEventLayer]:
        """Convert decision layer names into event-layer enum values."""
        layers: list[InitiativeEventLayer] = []
        for layer_name in decision.preferred_event_layers:
            try:
                layers.append(InitiativeEventLayer(layer_name))
            except ValueError:
                logger.warning("Unknown initiative event layer from decision: %s", layer_name)
        return layers

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

    def get_context(self, user_input: str = "") -> RuntimeContext:
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
            user_input=user_input,
        )

    def reset(self) -> None:
        """重置运行时状态。"""
        self.engine.reset_context()
        self._last_tick_time = time.time()
        if self.initiative_engine:
            self.initiative_engine.reset_cooldown()
        self.continuity.reset()
