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
from core.initiative.event_system import (
    InitiativeEvent,
    InitiativeEventLayer,
    ThreeLayerInitiativeEventSystem,
)
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
        appraisal_memory = self.memory.get_memory_summary(
            limit=min(self.prompt_builder.config.max_memory_lines, 6),
            query=user_input,
        )
        self.heart_lake_updater.on_user_input(
            user_input,
            memory_summary=appraisal_memory,
        )
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
        self._capture_relationship_continuity(user_input, result.content)
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
        event = self._select_initiative_event(decision)
        self._apply_initiative_event(event)
        event_context = self._build_initiative_event_context(event)
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
        content = (result.content or "").strip()
        if decision.intent == "presence_murmur":
            content = await self._ensure_unique_presence_murmur(
                content=content,
                system_prompt=system_prompt,
                runtime_context=context,
            )

        if content:
            if decision.intent == "presence_murmur":
                self.continuity.record_presence_murmur(content)
            self.continuity.record_assistant_message(
                content,
                proactive=True,
            )

        return content

    async def _ensure_unique_presence_murmur(
        self,
        *,
        content: str,
        system_prompt: str,
        runtime_context: RuntimeContext,
    ) -> Optional[str]:
        """Retry once when a presence murmur exactly repeats recent wording."""
        content = (content or "").strip()
        if not content:
            self._drop_unsent_assistant_message("")
            return await self._retry_presence_murmur(
                system_prompt=system_prompt,
                runtime_context=runtime_context,
                reason="刚才没有生成可投递的碎碎念。",
            )
        if not self._is_deliverable_presence_murmur(content):
            self._drop_unsent_assistant_message(content)
            return await self._retry_presence_murmur(
                system_prompt=system_prompt,
                runtime_context=runtime_context,
                reason=(
                    "刚才这句不适合作为 Presence Murmur：它可能像提问、话题推荐、"
                    f"新闻/链接/任务或太长：{content}"
                ),
            )
        if not self.continuity.has_recent_presence_murmur(content):
            return content

        self._drop_unsent_assistant_message(content)
        return await self._retry_presence_murmur(
            system_prompt=system_prompt,
            runtime_context=runtime_context,
            reason=f"刚才这句和已经发过的碎碎念完全相同：{content}",
        )

    async def _retry_presence_murmur(
        self,
        *,
        system_prompt: str,
        runtime_context: RuntimeContext,
        reason: str,
    ) -> Optional[str]:
        """Retry one presence murmur with strict deliverability constraints."""
        retry_prompt = (
            f"{system_prompt}\n\n"
            "【碎碎念可投递要求】\n"
            f"{reason}\n"
            "请换成另一句独一无二的短句。可以表达相同意思，但不能复用完全相同的句子。\n"
            "只能像轻轻冒泡一样说一句；不要问问题；不要要求远回复；不要提新闻、搜索、链接、天气、资料、视频、新发布内容或推荐；不要提出任务或计划。"
        )
        retry_result = await self.engine.respond(
            user_input="",
            system_prompt=retry_prompt,
            runtime_context=runtime_context,
        )
        retry_content = (retry_result.content or "").strip()
        if (
            retry_content
            and self._is_deliverable_presence_murmur(retry_content)
            and not self.continuity.has_recent_presence_murmur(retry_content)
        ):
            return retry_content

        if retry_content:
            self._drop_unsent_assistant_message(retry_content)
        logger.info("Suppressed undeliverable presence murmur: %s", retry_content)
        return self._fallback_unique_presence_murmur()

    def _is_deliverable_presence_murmur(self, content: str) -> bool:
        """Return whether generated text is safe to deliver as a light murmur."""
        text = " ".join((content or "").strip().split())
        if not text:
            return False
        if len(text) > 80:
            return False
        forbidden_tokens = (
            "新闻",
            "热点",
            "搜索",
            "链接",
            "资料",
            "视频",
            "天气",
            "新发布",
            "感兴趣",
            "我可以把",
            "发给你",
            "推荐",
            "天气怎么样",
            "怎么样",
            "要不要",
            "任务",
            "计划",
            "第一步",
            "第二步",
            "工具调用",
            "life_event_material",
            "initiative_decision",
            "expression_context",
            "generation_boundary",
        )
        if any(token in text for token in forbidden_tokens):
            return False
        if "？" in text or "?" in text:
            return False
        return True

    def _fallback_unique_presence_murmur(self) -> Optional[str]:
        """Generate a short unique murmur when the LLM gives no deliverable text."""
        starts = (
            "戳一下",
            "云汐冒个泡",
            "路过贴一下",
            "小小探头",
            "轻轻晃一下爪",
            "悄悄闪现一下",
        )
        middles = (
            "我在这儿呢",
            "陪你一小会儿",
            "不打扰你啦",
            "就是想让你看见我一下",
            "嘿嘿，云汐还在线",
            "给远晃一条小尾巴",
        )
        endings = ("～", "。", "，然后乖乖缩回去。", "，就一下。")
        total = len(starts) * len(middles) * len(endings)
        recent_count = len(getattr(self.continuity, "recent_presence_murmurs", []))
        seed = int(time.time() * 1000) + recent_count * 37
        for offset in range(total):
            index = (seed + offset) % total
            ending = endings[index % len(endings)]
            middle_index = (index // len(endings)) % len(middles)
            start_index = (index // (len(endings) * len(middles))) % len(starts)
            phrase = f"{starts[start_index]}，{middles[middle_index]}{ending}"
            if not self.continuity.has_recent_presence_murmur(phrase):
                return phrase

        phrase = f"云汐轻轻冒泡一下，给远第 {recent_count + 1} 条不重复的小尾巴。"
        if self.continuity.has_recent_presence_murmur(phrase):
            return None
        return phrase

    def _drop_unsent_assistant_message(self, content: str) -> None:
        """Remove a generated assistant message that will not be delivered."""
        context = getattr(self.engine, "context", None)
        messages = getattr(context, "messages", None)
        if not messages:
            return
        last_message = messages[-1]
        last_content = getattr(last_message, "content", "")
        text = ""
        if isinstance(last_content, list):
            text = "".join(str(getattr(block, "text", "")) for block in last_content)
        else:
            text = str(last_content)
        if text != content:
            return
        messages.pop()
        turn_count = int(getattr(context, "turn_count", 0))
        if turn_count > 0:
            context.turn_count = turn_count - 1

    def _select_initiative_event(self, decision: InitiativeDecision) -> InitiativeEvent | None:
        """Select one life event for proactive generation."""
        if self.initiative_event_system is None or not decision.should_select_event:
            return None
        preferred_layers = self._event_layers_from_decision(decision)
        event = self.initiative_event_system.select_event(
            preferred_layers=preferred_layers,
            required_tags=decision.required_event_tags,
        )
        if event is None and decision.required_event_tags:
            event = self.initiative_event_system.select_event(
                preferred_layers=preferred_layers,
            )
        return event

    def _build_initiative_event_context(self, event: InitiativeEvent | None) -> str:
        """Build selected life event prompt context."""
        if self.initiative_event_system is None:
            return ""
        return self.initiative_event_system.build_prompt_context(event)

    def _apply_initiative_event(self, event: InitiativeEvent | None) -> None:
        """Apply selected event affect and persist continuity context."""
        if event is None:
            return
        self.heart_lake.apply_affect_delta(
            valence=event.affect_delta.valence,
            arousal=event.affect_delta.arousal,
        )
        self.continuity.record_initiative_event(
            event_id=event.event_id,
            category=event.category,
            seed=event.seed,
            affect_valence=event.affect_delta.valence,
            affect_arousal=event.affect_delta.arousal,
        )

    def _capture_relationship_continuity(
        self,
        user_input: str,
        assistant_message: str,
    ) -> None:
        """Capture durable memory and continuity cues after a normal chat turn."""
        self.memory.capture_relationship_memory(user_input, assistant_message)
        self.continuity.capture_user_continuity(user_input)

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
            limit=self.prompt_builder.config.max_memory_lines,
            query=user_input,
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
