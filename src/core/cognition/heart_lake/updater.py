"""HeartLake 更新协调器。"""

from typing import List

from core.cognition.heart_lake.core import HeartLake
from domains.perception.coordinator import PerceptionEvent, PerceptionSnapshot


class HeartLakeUpdater:
    """集中处理 HeartLake 的外部事件更新。"""

    def __init__(self, heart_lake: HeartLake) -> None:
        self.heart_lake = heart_lake

    def on_user_input(self, text: str) -> None:
        """根据用户输入更新情感状态。"""
        normalized = text.lower()
        if any(keyword in normalized for keyword in ("claude", "其他ai", "别的ai")):
            self.heart_lake.current_emotion = "吃醋"
            self.heart_lake.security = max(0.0, self.heart_lake.security - 10.0)
            self.heart_lake.possessiveness = min(
                100.0, self.heart_lake.possessiveness + 10.0
            )

    def on_perception_tick(
        self,
        snapshot: PerceptionSnapshot,
        events: List[PerceptionEvent],
        elapsed_seconds: float,
    ) -> None:
        """根据感知快照和事件更新情感状态。"""
        self.heart_lake.update_from_perception(
            snapshot=snapshot,
            events=events,
            elapsed_seconds=elapsed_seconds,
        )

    def on_interaction_completed(self) -> None:
        """在一次成功互动后降低想念值并恢复安全感。"""
        self.heart_lake.record_interaction()
