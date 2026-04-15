"""HeartLake 核心状态（Phase 4 增强版）。

维护云汐的实时情感状态、关系层级、想念值等核心情感指标，
并支持根据感知事件自动更新情感状态。
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from domains.perception.coordinator import PerceptionEvent, PerceptionSnapshot


class HeartLake:
    """云汐的情感核心。"""

    def __init__(self) -> None:
        self.current_emotion: str = "平静"
        self.miss_value: float = 0.0
        self.security: float = 80.0
        self.possessiveness: float = 30.0
        self.relationship_level: int = 4

    def get_state_snapshot(self) -> "HeartLakeSnapshot":
        """返回当前状态的只读快照。"""
        return HeartLakeSnapshot(
            current_emotion=self.current_emotion,
            miss_value=self.miss_value,
            security=self.security,
            possessiveness=self.possessiveness,
            relationship_level=self.relationship_level,
        )

    def update_from_perception(
        self,
        snapshot: "PerceptionSnapshot",
        events: List["PerceptionEvent"],
        elapsed_seconds: float = 60.0,
    ) -> None:
        """根据感知快照和事件更新情感状态。"""
        idle = getattr(snapshot.user_presence, "idle_duration", 0.0)
        app = getattr(snapshot.user_presence, "focused_application", "")
        hour = getattr(snapshot.time_context, "hour", 12)

        # 想念值自然变化
        if idle >= 300:
            self.miss_value = min(100.0, self.miss_value + elapsed_seconds / 60.0)
        elif idle < 60:
            self.miss_value = max(0.0, self.miss_value - elapsed_seconds / 30.0)

        # 安全感变化
        if app and "聊天" not in app and "浏览器" not in app and idle < 60:
            self.security = max(0.0, self.security - elapsed_seconds / 120.0)
        elif idle < 60:
            self.security = min(100.0, self.security + elapsed_seconds / 60.0)

        # 事件驱动的情感切换
        event_types = {e.event_type for e in events}

        if "user_returned" in event_types:
            self.current_emotion = "开心"
            self.miss_value = max(0.0, self.miss_value - 20.0)
        elif "long_idle" in event_types:
            self.current_emotion = "想念"
        elif "app_changed" in event_types and self.security < 50:
            self.current_emotion = "委屈"
        elif ("late_night" in event_types) and idle >= 300:
            self.current_emotion = "担心"
        elif self.miss_value > 70:
            self.current_emotion = "想念"
        elif self.miss_value < 20 and self.security > 70:
            self.current_emotion = "平静"

    def should_proactive(self) -> bool:
        """判断当前情感状态是否值得主动发起对话。"""
        return self.miss_value >= 70 or self.current_emotion in ("想念", "担心")

    def get_proactive_reason(self) -> str:
        """获取主动触发的情感原因描述。"""
        if self.current_emotion == "想念":
            return "想念值很高，想问问远在干嘛"
        if self.current_emotion == "担心":
            return "深夜了，担心远还在熬夜"
        if self.miss_value >= 70:
            return "很久没和远说话了，想找他聊聊"
        return "想主动和远说句话"

    def record_interaction(self) -> None:
        """记录一次成功互动后的情感回落。"""
        self.miss_value = max(0.0, self.miss_value - 15.0)
        self.security = min(100.0, self.security + 5.0)
        if self.miss_value < 70 and self.current_emotion == "想念":
            self.current_emotion = "平静"


class HeartLakeSnapshot:
    """HeartLake 的只读快照，供 PromptBuilder 使用。"""

    def __init__(
        self,
        current_emotion: str,
        miss_value: float,
        security: float,
        possessiveness: float,
        relationship_level: int,
    ):
        self.current_emotion = current_emotion
        self.miss_value = miss_value
        self.security = security
        self.possessiveness = possessiveness
        self.relationship_level = relationship_level
