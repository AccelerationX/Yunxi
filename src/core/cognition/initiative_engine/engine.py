"""主动触发引擎（InitiativeEngine）。

根据 HeartLake 情感状态与感知事件，判断云汐是否应主动发起对话。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.cognition.heart_lake.core import HeartLake
    from domains.perception.coordinator import PerceptionEvent


@dataclass
class InitiativeDecision:
    """主动触发决策结果。"""

    trigger: bool
    reason: str
    urgency: float = 0.0


class InitiativeEngine:
    """主动触发引擎。"""

    def __init__(self, cooldown_seconds: float = 300.0):
        self.cooldown_seconds = cooldown_seconds
        self._last_trigger_time: Optional[float] = None

    def evaluate(
        self,
        heart_lake: "HeartLake",
        events: List["PerceptionEvent"],
        current_time: float,
        unanswered_proactive_count: int = 0,
    ) -> InitiativeDecision:
        """评估当前状态，返回是否应主动触发对话。"""
        if self._is_in_cooldown(current_time):
            return InitiativeDecision(
                trigger=False, reason="处于冷却期", urgency=0.0
            )

        if unanswered_proactive_count >= 3:
            return InitiativeDecision(
                trigger=False,
                reason="已连续主动 3 次未获回复，进入冷静期",
                urgency=0.0,
            )

        event_types = {e.event_type for e in events}
        urgency = 0.0
        reason = ""

        # 高优先级事件
        if "user_returned" in event_types and heart_lake.miss_value > 50:
            urgency = 0.8
            reason = "用户刚回来，想念值又很高，想打个招呼"
        elif "long_idle" in event_types and heart_lake.miss_value >= 60:
            urgency = 0.7
            reason = "用户离开很久了，有点想念他"
        elif heart_lake.current_emotion == "担心":
            urgency = 0.75
            reason = "深夜还在忙，想提醒他休息"
        elif heart_lake.should_proactive():
            urgency = 0.6
            reason = heart_lake.get_proactive_reason()

        if urgency > 0:
            self._last_trigger_time = current_time
            return InitiativeDecision(trigger=True, reason=reason, urgency=urgency)

        return InitiativeDecision(trigger=False, reason="暂无主动触发必要", urgency=0.0)

    def _is_in_cooldown(self, current_time: float) -> bool:
        if self._last_trigger_time is None:
            return False
        return (current_time - self._last_trigger_time) < self.cooldown_seconds

    def reset_cooldown(self) -> None:
        """重置冷却时间（测试用）。"""
        self._last_trigger_time = None
