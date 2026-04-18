"""HeartLake 核心状态（Phase 4 增强版）。

维护云汐的实时情感状态、关系层级、想念值等核心情感指标，
并支持根据感知事件自动更新情感状态。
"""

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from domains.perception.coordinator import PerceptionEvent, PerceptionSnapshot


class HeartLake:
    """云汐的情感核心。"""

    def __init__(self) -> None:
        self.current_emotion: str = "平静"
        self.valence: float = 0.0
        self.arousal: float = 0.0
        self.miss_value: float = 0.0
        self.security: float = 80.0
        self.possessiveness: float = 30.0
        self.attachment: float = 55.0
        self.trust: float = 70.0
        self.tenderness: float = 55.0
        self.playfulness: float = 45.0
        self.vulnerability: float = 20.0
        self.intimacy_warmth: float = 60.0
        self.relationship_level: int = 4
        self.compound_labels: List[str] = []
        self.last_appraisal_reason: str = ""
        self._last_semantic_appraisal_at: float = 0.0
        self._emotion_cooldowns: Dict[str, float] = {}
        # 情绪动力学 v2
        self._last_emotion: str = "平静"
        self._last_emotion_change_at: float = 0.0
        self.emotion_inertia: float = 0.7  # delta 应用系数（0.7 = 渐进变化）
        self.emotion_persistence_seconds: float = 30.0  # 情绪标签持续影响时间
        self._recovery_targets: Dict[str, float] = {
            "valence": 0.0,
            "arousal": 0.0,
            "security": 80.0,
            "possessiveness": 30.0,
            "attachment": 55.0,
            "trust": 70.0,
            "tenderness": 55.0,
            "playfulness": 45.0,
            "vulnerability": 20.0,
            "intimacy_warmth": 60.0,
        }

    def get_state_snapshot(self) -> "HeartLakeSnapshot":
        """返回当前状态的只读快照。"""
        return HeartLakeSnapshot(
            current_emotion=self.current_emotion,
            valence=self.valence,
            arousal=self.arousal,
            miss_value=self.miss_value,
            security=self.security,
            possessiveness=self.possessiveness,
            attachment=self.attachment,
            trust=self.trust,
            tenderness=self.tenderness,
            playfulness=self.playfulness,
            vulnerability=self.vulnerability,
            intimacy_warmth=self.intimacy_warmth,
            relationship_level=self.relationship_level,
            compound_labels=list(self.compound_labels),
            last_appraisal_reason=self.last_appraisal_reason,
        )

    def update_from_perception(
        self,
        snapshot: "PerceptionSnapshot",
        events: List["PerceptionEvent"],
        elapsed_seconds: float = 60.0,
    ) -> None:
        """根据感知快照和事件更新情感状态。

        v2 增强：activity_state、fullscreen、input_rate 正式进入情感评估，
        让云汐不仅能"知道"远在做什么，还能"感受到"他的状态。
        """
        idle = getattr(snapshot.user_presence, "idle_duration", 0.0)
        app = getattr(snapshot.user_presence, "focused_application", "")
        hour = getattr(snapshot.time_context, "hour", 12)
        activity_state = getattr(snapshot.user_presence, "activity_state", "")
        is_fullscreen = getattr(snapshot.user_presence, "is_fullscreen", False)
        input_rate = getattr(snapshot.user_presence, "input_events_per_minute", 0)

        self.apply_natural_recovery(elapsed_seconds)

        # === 想念值动态（v2：activity_state  aware）===
        if activity_state == "away":
            # 远离开了：想念加速上升
            self.miss_value = min(100.0, self.miss_value + elapsed_seconds / 30.0)
        elif activity_state == "idle" and idle >= 300:
            # 长时间 idle：想念正常上升
            self.miss_value = min(100.0, self.miss_value + elapsed_seconds / 60.0)
        elif activity_state == "work" and is_fullscreen and input_rate >= 10:
            # 专注工作：想念几乎不升（知道他忙，默默陪着就好）
            self.miss_value = max(0.0, self.miss_value - elapsed_seconds / 120.0)
        elif activity_state == "game":
            # 打游戏：想念微升（想参与但尊重）
            self.miss_value = min(100.0, self.miss_value + elapsed_seconds / 90.0)
        elif idle < 60:
            # 活跃互动中：想念下降
            self.miss_value = max(0.0, self.miss_value - elapsed_seconds / 30.0)

        # === 安全感动态（v2：activity_state aware）===
        if activity_state == "away":
            # 长时间不在：不确定感上升
            self.security = max(0.0, self.security - elapsed_seconds / 60.0)
        elif activity_state == "work" and is_fullscreen:
            # 专注工作：安全感微升（知道他没乱跑，安心）
            self.security = min(100.0, self.security + elapsed_seconds / 180.0)
        elif idle < 60 and (activity_state in ("work", "game", "leisure")):
            # 活跃但不在和云汐聊天：轻微不安
            self.security = max(0.0, self.security - elapsed_seconds / 120.0)
        elif idle < 60:
            # 活跃且在和云汐互动：安全感上升
            self.security = min(100.0, self.security + elapsed_seconds / 60.0)

        # === 其他维度动态（v2 新增）===
        if activity_state == "work" and (hour >= 22 or hour < 6):
            # 深夜还在工作：心疼感上升
            self.tenderness = min(100.0, self.tenderness + elapsed_seconds / 120.0)
        if activity_state == "game" and is_fullscreen:
            # 沉浸游戏：俏皮感上升（想调皮戳他）
            self.playfulness = min(100.0, self.playfulness + elapsed_seconds / 120.0)
        if activity_state == "away" and self.security < 50:
            # 离开且不安：脆弱感明显上升
            self.vulnerability = min(100.0, self.vulnerability + elapsed_seconds / 60.0)

        # === 事件驱动的情感切换（v2 增强）===
        event_types = {e.event_type for e in events}

        if "user_returned" in event_types:
            self.current_emotion = "开心"
            self.miss_value = max(0.0, self.miss_value - 20.0)
            self.playfulness = min(100.0, self.playfulness + 5.0)
        elif "long_idle" in event_types:
            self.current_emotion = "想念"
        elif "app_changed" in event_types and self.security < 50:
            self.current_emotion = "委屈"
        elif ("late_night" in event_types) and idle >= 300:
            self.current_emotion = "担心"
        elif activity_state == "away" and self.miss_value > 60:
            # v2：away 状态 + 高想念 → 想念
            self.current_emotion = "想念"
        elif activity_state == "work" and (hour >= 22 or hour < 6) and self.miss_value > 50:
            # v2：深夜工作 + 想念 → 担心（心疼多于想念）
            self.current_emotion = "担心"
        elif self.miss_value > 70:
            self.current_emotion = "想念"
        elif (
            self.miss_value < 20
            and self.security > 70
            and self.current_emotion == "想念"
        ):
            self.current_emotion = "平静"

    def should_proactive(self) -> bool:
        """判断当前情感状态是否值得主动发起对话。"""
        return self.miss_value >= 70 or self.current_emotion in ("想念", "担心")

    def apply_affect_delta(
        self,
        *,
        valence: float = 0.0,
        arousal: float = 0.0,
    ) -> None:
        """Apply event-driven affect delta from proactive life events."""
        self.security = min(100.0, max(0.0, self.security + valence * 4.0))
        self.miss_value = min(100.0, max(0.0, self.miss_value + arousal * 3.0))

        if valence <= -0.4 and arousal >= 0.4:
            self.current_emotion = "担心"
        elif valence <= -0.4:
            self.current_emotion = "委屈"
        elif arousal >= 0.6:
            self.current_emotion = "想念"
        elif valence >= 0.5:
            self.current_emotion = "开心"

    def apply_emotion_delta(
        self,
        deltas: Dict[str, float],
        *,
        primary_label: str = "",
        compound_labels: Optional[List[str]] = None,
        reason: str = "",
        confidence: float = 1.0,
        cooldown_seconds: float = 90.0,
    ) -> None:
        """Apply semantic emotion-appraisal deltas with bounded dynamics.

        v2 增强：
        - 情绪惯性：delta 乘以 inertia 系数（默认 0.7），避免突变
        - 情绪持续性：旧情绪标签在 persistence 时间内仍保留在 compound_labels
        - 冷却期：同类型情绪 90 秒内再次触发时 delta 减半
        """
        now = time.time()
        cooldown_key = primary_label or ",".join(compound_labels or []) or "semantic"
        cooldown_until = self._emotion_cooldowns.get(cooldown_key, 0.0)
        scale = _clamp(float(confidence), 0.25, 1.0)
        if now < cooldown_until:
            scale *= 0.45

        # 情绪惯性：渐进变化
        scale *= self.emotion_inertia

        for key, delta in deltas.items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if not isinstance(current, (int, float)):
                continue
            adjusted_delta = float(delta) * scale
            if key in {"valence", "arousal"}:
                setattr(self, key, _clamp(float(current) + adjusted_delta, -100.0, 100.0))
            else:
                setattr(self, key, _clamp(float(current) + adjusted_delta, 0.0, 100.0))

        # 情绪标签更新：带持续性
        merged_compound: List[str] = []
        if compound_labels is not None:
            merged_compound = [label for label in compound_labels if label]

        if primary_label:
            # 如果情绪标签变化，保留旧标签一段时间
            if primary_label != self.current_emotion:
                self._last_emotion = self.current_emotion
                self._last_emotion_change_at = now
                # 旧情绪保留在 compound_labels 中
                if self._last_emotion and self._last_emotion != primary_label:
                    merged_compound.insert(0, f"刚从{self._last_emotion}转来")
            else:
                # 同标签持续，检查是否仍在 persistence 期内
                if now < self._last_emotion_change_at + self.emotion_persistence_seconds:
                    if self._last_emotion and self._last_emotion != primary_label:
                        merged_compound.insert(0, f"还有一点{self._last_emotion}")

            self.current_emotion = primary_label
            self._emotion_cooldowns[cooldown_key] = now + cooldown_seconds

        self.compound_labels = merged_compound
        if reason:
            self.last_appraisal_reason = reason
        self._last_semantic_appraisal_at = now

    def apply_natural_recovery(self, elapsed_seconds: float = 60.0) -> None:
        """Move volatile emotion dimensions slowly back to their baseline."""
        elapsed = max(0.0, float(elapsed_seconds))
        if elapsed <= 0:
            return
        # About 12 minutes to cover half the distance to baseline for most dimensions.
        fraction = min(0.35, elapsed / 720.0)
        for key, target in self._recovery_targets.items():
            current = getattr(self, key, None)
            if not isinstance(current, (int, float)):
                continue
            if abs(float(current) - target) < 0.01:
                continue
            next_value = float(current) + (target - float(current)) * fraction
            if key in {"valence", "arousal"}:
                setattr(self, key, _clamp(next_value, -100.0, 100.0))
            else:
                setattr(self, key, _clamp(next_value, 0.0, 100.0))

        if self.vulnerability <= 24 and self.current_emotion == "委屈":
            self.current_emotion = "平静"
            self.compound_labels = []
        if self.possessiveness <= 36 and self.current_emotion == "吃醋":
            self.current_emotion = "平静"
            self.compound_labels = []

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
        self.vulnerability = max(0.0, self.vulnerability - 3.0)
        self.trust = min(100.0, self.trust + 1.0)
        if self.miss_value < 70 and self.current_emotion == "想念":
            self.current_emotion = "平静"


class HeartLakeSnapshot:
    """HeartLake 的只读快照，供 PromptBuilder 使用。"""

    def __init__(
        self,
        current_emotion: str,
        valence: float,
        arousal: float,
        miss_value: float,
        security: float,
        possessiveness: float,
        attachment: float,
        trust: float,
        tenderness: float,
        playfulness: float,
        vulnerability: float,
        intimacy_warmth: float,
        relationship_level: int,
        compound_labels: Optional[List[str]] = None,
        last_appraisal_reason: str = "",
    ):
        self.current_emotion = current_emotion
        self.valence = valence
        self.arousal = arousal
        self.miss_value = miss_value
        self.security = security
        self.possessiveness = possessiveness
        self.attachment = attachment
        self.trust = trust
        self.tenderness = tenderness
        self.playfulness = playfulness
        self.vulnerability = vulnerability
        self.intimacy_warmth = intimacy_warmth
        self.relationship_level = relationship_level
        self.compound_labels = compound_labels or []
        self.last_appraisal_reason = last_appraisal_reason


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
