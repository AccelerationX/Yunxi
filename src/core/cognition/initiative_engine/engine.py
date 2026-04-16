"""Initiative trigger engine for Yunxi.

The engine decides whether Yunxi should start a proactive conversation by
looking at emotion, perception, continuity, unanswered messages, and interrupt
cost. It does not generate user-visible text; it only returns decision context
for the LLM prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.cognition.heart_lake.core import HeartLake
    from core.initiative.continuity import CompanionContinuityService
    from domains.perception.coordinator import PerceptionEvent, PerceptionSnapshot


DEFAULT_DAILY_PROACTIVE_BUDGET = 5
TRIGGER_THRESHOLD = 0.55


@dataclass
class InitiativeDecision:
    """Proactive trigger decision."""

    trigger: bool
    reason: str
    urgency: float = 0.0
    intent: str = "general_checkin"
    expression_mode: str = "natural"
    preferred_event_layers: tuple[str, ...] = field(default_factory=tuple)
    required_event_tags: tuple[str, ...] = field(default_factory=tuple)
    should_select_event: bool = True
    suppression_reason: str = ""


class InitiativeEngine:
    """Evaluate whether Yunxi should proactively start a conversation."""

    def __init__(
        self,
        cooldown_seconds: float = 300.0,
        daily_budget: int = DEFAULT_DAILY_PROACTIVE_BUDGET,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.daily_budget = daily_budget
        self._last_trigger_time: Optional[float] = None

    def evaluate(
        self,
        heart_lake: "HeartLake",
        events: List["PerceptionEvent"],
        current_time: float,
        unanswered_proactive_count: int = 0,
        perception_snapshot: Optional["PerceptionSnapshot"] = None,
        continuity: Optional["CompanionContinuityService"] = None,
    ) -> InitiativeDecision:
        """Evaluate runtime state and return a proactive decision."""
        if self._is_in_cooldown(current_time):
            return InitiativeDecision(
                trigger=False,
                reason="处于冷却期",
                urgency=0.0,
                should_select_event=False,
                suppression_reason="cooldown",
            )

        if unanswered_proactive_count >= 3:
            return InitiativeDecision(
                trigger=False,
                reason="已连续主动 3 次未获回复，进入冷静期",
                urgency=0.0,
                expression_mode="quiet",
                should_select_event=False,
                suppression_reason="too_many_unanswered",
            )

        if continuity is not None and hasattr(continuity, "refresh_daily_proactive_count"):
            continuity.refresh_daily_proactive_count(current_time)
        recent_proactive_count = getattr(continuity, "recent_proactive_count", 0)
        if recent_proactive_count >= self.daily_budget:
            return InitiativeDecision(
                trigger=False,
                reason="今日主动次数已经足够，保持克制",
                urgency=0.0,
                expression_mode="quiet",
                should_select_event=False,
                suppression_reason="daily_budget_exhausted",
            )

        decision = self._score_decision(
            heart_lake=heart_lake,
            events=events,
            unanswered_proactive_count=unanswered_proactive_count,
            perception_snapshot=perception_snapshot,
            continuity=continuity,
        )
        if decision.trigger:
            self._last_trigger_time = current_time
        return decision

    def _score_decision(
        self,
        *,
        heart_lake: "HeartLake",
        events: List["PerceptionEvent"],
        unanswered_proactive_count: int,
        perception_snapshot: Optional["PerceptionSnapshot"],
        continuity: Optional["CompanionContinuityService"],
    ) -> InitiativeDecision:
        event_types = {event.event_type for event in events}
        score = 0.0
        reasons: list[str] = []
        intent = "general_checkin"
        expression_mode = "natural"
        preferred_layers: tuple[str, ...] = ("inner_life", "mixed")
        required_tags: tuple[str, ...] = ()

        if "user_returned" in event_types and heart_lake.miss_value > 50:
            score += 0.55
            reasons.append("远刚回到电脑前，想念值也偏高")
            intent = "welcome_back"
            expression_mode = "warm_reunion"
            preferred_layers = ("mixed", "shared_interest")
        elif "long_idle" in event_types and heart_lake.miss_value >= 60:
            score += 0.35
            reasons.append("远离开了一段时间，云汐有点想念")
            intent = "miss_after_idle"
            expression_mode = "soft_checkin"

        if "late_night" in event_types:
            score += 0.20
            reasons.append("现在已经偏晚")
            required_tags = ("深夜", "关心")

        emotion = getattr(heart_lake, "current_emotion", "平静")
        miss_value = float(getattr(heart_lake, "miss_value", 0.0))
        if emotion == "担心":
            score += 0.45
            reasons.append("云汐正在担心远")
            intent = "care"
            expression_mode = "gentle_care"
            required_tags = ("关心",)
        elif emotion == "想念":
            score += 0.30
            reasons.append("云汐正在想念远")
            intent = "missing"
            expression_mode = "soft_missing"
        elif emotion == "吃醋":
            score += 0.25
            reasons.append("云汐有一点吃醋")
            intent = "affectionate_jealousy"
            expression_mode = "light_jealousy"

        if miss_value >= 85:
            score += 0.45
            reasons.append("想念值很高")
            intent = "missing"
        elif miss_value >= 70:
            score += 0.30
            reasons.append("已经有一段时间没有自然聊天")

        if continuity is not None:
            if continuity.comfort_needed:
                score += 0.40
                reasons.append("连续性状态显示远可能需要安慰")
                intent = "comfort"
                expression_mode = "gentle_care"
                required_tags = ("安慰", "关心")
            if continuity.get_open_threads():
                score += 0.25
                reasons.append("你们还有未完成的话题")
                intent = "continue_thread"
                preferred_layers = ("shared_interest", "mixed")
            if continuity.proactive_cues:
                score += 0.25
                reasons.append("存在之前留下的主动话题线索")
                intent = "follow_cue"
                preferred_layers = ("shared_interest", "mixed")
            if continuity.fragmented_chat:
                score -= 0.15
                reasons.append("最近对话较碎片化，需要降低打扰感")
                expression_mode = "restrained_followup"
            if continuity.task_focus:
                score -= 0.15
                reasons.append("远当前有明确任务焦点")
                expression_mode = "low_interrupt"

        if unanswered_proactive_count > 0:
            score -= 0.20 * unanswered_proactive_count
            reasons.append("之前的主动还没有得到回应，需要更克制")
            expression_mode = "restrained_followup"

        score += self._presence_score(perception_snapshot, reasons)

        if score < TRIGGER_THRESHOLD:
            return InitiativeDecision(
                trigger=False,
                reason="; ".join(reasons) or "暂无主动触发必要",
                urgency=max(0.0, round(score, 2)),
                intent=intent,
                expression_mode=expression_mode,
                preferred_event_layers=preferred_layers,
                required_event_tags=required_tags,
                should_select_event=False,
                suppression_reason="score_below_threshold",
            )

        return InitiativeDecision(
            trigger=True,
            reason="; ".join(reasons),
            urgency=min(1.0, round(score, 2)),
            intent=intent,
            expression_mode=expression_mode,
            preferred_event_layers=preferred_layers,
            required_event_tags=required_tags,
            should_select_event=True,
        )

    def _presence_score(
        self,
        perception_snapshot: Optional["PerceptionSnapshot"],
        reasons: list[str],
    ) -> float:
        if perception_snapshot is None:
            return 0.0
        user_presence = getattr(perception_snapshot, "user_presence", None)
        if user_presence is None:
            return 0.0
        idle_duration = float(getattr(user_presence, "idle_duration", 0.0) or 0.0)
        focused_application = str(getattr(user_presence, "focused_application", "") or "")
        if idle_duration >= 300:
            reasons.append("远已经离开键盘一段时间")
            return 0.15
        if focused_application and idle_duration < 30:
            reasons.append("远正在电脑前专注操作，打扰成本较高")
            return -0.20
        return 0.0

    def _is_in_cooldown(self, current_time: float) -> bool:
        if self._last_trigger_time is None:
            return False
        return (current_time - self._last_trigger_time) < self.cooldown_seconds

    def reset_cooldown(self) -> None:
        """Reset cooldown timestamp for tests and runtime restart paths."""
        self._last_trigger_time = None
