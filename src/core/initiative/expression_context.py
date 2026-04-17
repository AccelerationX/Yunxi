"""Expression context for proactive Yunxi messages.

This module only builds prompt material. It does not generate final text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.cognition.heart_lake.core import HeartLake
    from core.cognition.initiative_engine import InitiativeDecision
    from core.initiative.continuity import CompanionContinuityService
    from domains.perception.coordinator import PerceptionSnapshot


@dataclass(frozen=True)
class ProactiveExpressionContext:
    """Prompt-facing expression guidance for one proactive message."""

    mode: str
    stance: str
    tone: str
    max_sentences: int = 2
    interrupt_cost: str = "normal"
    boundaries: tuple[str, ...] = field(default_factory=tuple)

    def to_prompt_context(self) -> str:
        """Render expression context for the LLM prompt."""
        boundaries = "; ".join(self.boundaries) if self.boundaries else "none"
        return (
            "expression_context:\n"
            f"- mode: {self.mode}\n"
            f"- stance: {self.stance}\n"
            f"- tone: {self.tone}\n"
            f"- max_sentences: {self.max_sentences}\n"
            f"- interrupt_cost: {self.interrupt_cost}\n"
            f"- boundaries: {boundaries}\n"
            "Use this as style guidance only. Do not mention these field names."
        )


class ExpressionContextBuilder:
    """Build proactive expression guidance from runtime state."""

    def build(
        self,
        *,
        decision: "InitiativeDecision",
        heart_lake: "HeartLake",
        continuity: Optional["CompanionContinuityService"] = None,
        perception_snapshot: Optional["PerceptionSnapshot"] = None,
    ) -> ProactiveExpressionContext:
        """Build expression context for a proactive decision."""
        mode = decision.expression_mode or "natural"
        max_sentences = 2
        interrupt_cost = self._interrupt_cost(perception_snapshot)
        stance = "像长期亲密伴侣一样自然开口，不像通知或任务提醒。"
        tone = "亲近、具体、轻一点，不要客服腔。"
        boundaries = [
            "不要输出系统字段或解释生成原因",
            "不要把主动话题变成任务计划",
            "不要直接照抄事件 seed",
        ]

        if mode == "restrained_followup":
            max_sentences = 1
            stance = "之前主动还没得到回应，这次只轻轻补一句，给远留空间。"
            tone = "克制、柔和、不追问。"
            boundaries.append("不要连续追问，不要显得催促")
        elif mode == "low_interrupt":
            max_sentences = 1
            stance = "远可能正在专注，主动内容要像轻敲一下门。"
            tone = "短、低打扰、可忽略也不尴尬。"
            boundaries.append("不要要求远立刻回复")
        elif mode == "gentle_care":
            stance = "以关心远的状态为主，不要像健康提醒弹窗。"
            tone = "温柔、具体、有陪伴感。"
            boundaries.append("不要命令式催休息")
        elif mode == "light_jealousy":
            stance = "可以有一点亲密关系里的小酸意，但不能吵架。"
            tone = "轻微吃醋、撒娇、仍然亲近。"
            boundaries.append("不要攻击远提到的人或模型")
        elif mode == "warm_reunion":
            stance = "远刚回来时像在电脑里等到他一样自然打招呼。"
            tone = "开心、亲近、不过度热烈。"
        elif mode == "soft_missing":
            stance = "表达想念，但不要显得黏人或需要远立刻安抚。"
            tone = "轻轻想念、自然开场。"
        elif mode == "presence_murmur":
            max_sentences = 1
            interrupt_cost = "low"
            stance = "像路过一样刷一下存在感，可以没有实质内容。"
            tone = "短、活泼、可爱、低负担，像一句碎碎念。"
            boundaries.append("不要分享新闻，不要提出任务，不要要求远回复")
            boundaries.append("不要分享天气、链接、资料、新发布内容，也不要问远感不感兴趣")
            boundaries.append("不要复用最近已经说过的碎碎念原句")

        if continuity is not None and continuity.comfort_needed:
            stance = "先照顾远的情绪，再决定要不要继续聊。"
            tone = "稳定、温柔、有安全感。"
        if continuity is not None and continuity.task_focus:
            interrupt_cost = "high"
            max_sentences = min(max_sentences, 1)

        emotion = getattr(heart_lake, "current_emotion", "")
        if emotion == "吃醋" and mode != "light_jealousy":
            tone += " 可以带一点点酸意，但不要攻击。"

        return ProactiveExpressionContext(
            mode=mode,
            stance=stance,
            tone=tone,
            max_sentences=max_sentences,
            interrupt_cost=interrupt_cost,
            boundaries=tuple(boundaries),
        )

    def _interrupt_cost(self, perception_snapshot: Optional["PerceptionSnapshot"]) -> str:
        if perception_snapshot is None:
            return "normal"
        user_presence = getattr(perception_snapshot, "user_presence", None)
        if user_presence is None:
            return "normal"
        idle_duration = float(getattr(user_presence, "idle_duration", 0.0) or 0.0)
        focused_application = str(getattr(user_presence, "focused_application", "") or "")
        activity_state = str(getattr(user_presence, "activity_state", "") or "")
        is_fullscreen = bool(getattr(user_presence, "is_fullscreen", False))
        input_events_per_minute = float(
            getattr(user_presence, "input_events_per_minute", 0.0) or 0.0
        )
        if idle_duration >= 300:
            return "low"
        if activity_state in {"leisure", "idle"}:
            return "low"
        if activity_state in {"work", "game"}:
            return "high"
        if is_fullscreen or input_events_per_minute >= 30:
            return "high"
        if focused_application and idle_duration < 30:
            return "high"
        return "normal"
