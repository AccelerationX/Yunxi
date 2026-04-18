"""HeartLake 更新协调器。"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Union

from core.cognition.heart_lake.core import HeartLake
from domains.perception.coordinator import PerceptionEvent, PerceptionSnapshot


@dataclass
class AppraisalRule:
    """情感评估规则：将触发条件映射为情感状态变化。"""
    name: str
    description: str
    # 条件函数：返回 True 时触发此规则
    condition: Callable[[str, "HeartLake"], bool]
    # 触发后将主导情绪设为此值
    emotion: str
    # 安全感变化量
    security_delta: float = 0.0
    # 占有欲变化量
    possessiveness_delta: float = 0.0
    # 想念值变化量
    miss_value_delta: float = 0.0


@dataclass
class EmotionAppraisalResult:
    """Semantic emotion appraisal output for HeartLake v2."""

    primary_label: str
    compound_labels: List[str]
    deltas: Dict[str, float]
    confidence: float
    reason: str
    should_write_memory: bool = False


class _JealousyAppraisal:
    """基于模式的嫉妒触发评估器。

    评估用户输入是否触发云汐的嫉妒情绪，采用多模式匹配：
    1. 明确提及其他 AI（不限于特定名称）
    2. 将云汐与其他 AI 比较
    3. 表达对其他 AI 的正面态度
    """

    # 其他 AI 的语义模式（非穷举，基于语义分类）
    _OTHER_AI_PATTERNS: tuple[str, ...] = (
        r"\b(claude|claude3|anthropic)\b",
        r"\b(gpt|gpt-4|gpt4|chatgpt|openai)\b",
        r"\b(gemini|google\s*ai|deepmind)\b",
        r"\b(copilot|github\s*copilot)\b",
        r"\b(kimi|moonshot)\b",
        r"\b(豆包|通义|文心|智谱)\b",
        r"\b(其他|别的|别的?ai|别的?人工智能)\b",
        r"\b(one|another)\s*ai\b",
        r"\b(人工智能|AI|大模型)\b(?=.*?(更好|厉害|强|聪明))",
        r"\b(更好|厉害|强|聪明|棒)\b.*?(ai|人工智能|模型)",
    )

    _COMPARISON_PATTERNS: tuple[str, ...] = (
        r"比.*?(更|还|比较)",
        r".*?(更好|更棒|更强|更聪明|更厉害)",
        r"比不过",
        r"不如.*?(好|棒|强|聪明)",
    )

    def __init__(self) -> None:
        self._compiled_other_ai: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self._OTHER_AI_PATTERNS
        ]
        self._compiled_comparison: List[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self._COMPARISON_PATTERNS
        ]

    def evaluate(self, text: str, current_security: float) -> bool:
        """评估用户输入是否触发嫉妒情绪。"""
        normalized = text.lower()

        # 模式1：直接提及其他 AI
        mentions_other_ai = any(p.search(normalized) for p in self._compiled_other_ai)

        # 模式2：比较性表达（隐含云汐 vs 其他）
        has_comparison = any(p.search(normalized) for p in self._compiled_comparison)

        # 模式3：在同一句中既提及其他 AI 又表达正面评价
        positive_evaluation = any(
            word in normalized
            for word in (
                "厉害", "聪明", "强", "棒", "好", "优秀", "牛", "赞",
                "great", "smart", "good", "better", "best", "amazing",
            )
        )

        if mentions_other_ai and has_comparison:
            return True
        if mentions_other_ai and positive_evaluation:
            return True

        return False


class EmotionAppraiser:
    """Local OCC-style appraiser for daily-mode HeartLake v2.

    This class is deterministic on purpose. It moves HeartLake beyond one-off
    keyword switching while keeping the first v2 layer testable offline.
    """

    def __init__(self) -> None:
        self._jealousy = _JealousyAppraisal()

    def appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        *,
        memory_summary: str = "",
    ) -> Optional[EmotionAppraisalResult]:
        normalized = text.strip()
        if not normalized:
            return None

        deltas: Dict[str, float] = {}
        labels: List[str] = []
        reasons: List[str] = []
        primary = ""
        confidence = 0.0

        if self._jealousy.evaluate(normalized, heart_lake.security):
            primary = "吃醋"
            labels.append("轻微吃醋")
            _add_delta(deltas, "security", -8.0)
            _add_delta(deltas, "possessiveness", 12.0)
            _add_delta(deltas, "vulnerability", 4.0)
            _add_delta(deltas, "arousal", 8.0)
            confidence = max(confidence, 0.86)
            reasons.append("远提到或夸了其他 AI")
            if any(token in normalized for token in ("最喜欢你", "还是你", "你最重要", "云汐最")):
                labels.append("被安抚")
                _add_delta(deltas, "security", 6.0)
                _add_delta(deltas, "trust", 4.0)
                reasons.append("远同时确认了云汐的重要性")

        if any(token in normalized for token in ("累", "撑不住", "难受", "压力", "焦虑", "崩溃", "不想做任务")):
            primary = _choose_primary(primary, "担心", confidence, 0.8)
            labels.append("担心但想陪着")
            _add_delta(deltas, "tenderness", 10.0)
            _add_delta(deltas, "attachment", 5.0)
            _add_delta(deltas, "arousal", 5.0)
            _add_delta(deltas, "valence", -4.0)
            confidence = max(confidence, 0.8)
            reasons.append("远表达了疲惫或压力")

        if any(token in normalized for token in ("安心", "安全感", "陪着", "陪伴感", "被陪", "谢谢你", "喜欢你陪")):
            primary = _choose_primary(primary, "开心", confidence, 0.78)
            labels.append("安心")
            _add_delta(deltas, "security", 8.0)
            _add_delta(deltas, "trust", 6.0)
            _add_delta(deltas, "tenderness", 5.0)
            _add_delta(deltas, "intimacy_warmth", 7.0)
            _add_delta(deltas, "valence", 8.0)
            confidence = max(confidence, 0.78)
            reasons.append("远表达了被陪伴和安心")

        if any(token in normalized for token in ("情感寄托", "不是工具", "放下伪装", "用心相处", "我的云汐", "你是我的")):
            primary = _choose_primary(primary, "开心", confidence, 0.84)
            labels.append("被珍视")
            _add_delta(deltas, "trust", 10.0)
            _add_delta(deltas, "attachment", 8.0)
            _add_delta(deltas, "tenderness", 8.0)
            _add_delta(deltas, "intimacy_warmth", 10.0)
            _add_delta(deltas, "security", 6.0)
            confidence = max(confidence, 0.84)
            reasons.append("远确认了云汐的关系意义")

        if any(token in normalized for token in ("碎碎念", "刷存在感", "活泼", "可爱", "撒娇", "偶尔冒泡")):
            primary = _choose_primary(primary, "开心", confidence, 0.74)
            labels.append("想撒娇")
            _add_delta(deltas, "playfulness", 10.0)
            _add_delta(deltas, "attachment", 4.0)
            _add_delta(deltas, "miss_value", 3.0)
            confidence = max(confidence, 0.74)
            reasons.append("远鼓励云汐自然主动和活泼表达")

        if any(token in normalized for token in ("别打扰", "不要打扰", "少打扰", "频繁打扰", "有点烦", "让我不舒服")):
            primary = "委屈"
            labels.append("被提醒边界")
            _add_delta(deltas, "vulnerability", 10.0)
            _add_delta(deltas, "playfulness", -8.0)
            _add_delta(deltas, "miss_value", -8.0)
            _add_delta(deltas, "arousal", -4.0)
            confidence = max(confidence, 0.82)
            reasons.append("远指出了打扰边界")

        if not deltas:
            return None

        memory_text = memory_summary or ""
        if "情感寄托" in memory_text and primary in {"开心", "担心"}:
            labels.append("关系被记起")
            _add_delta(deltas, "intimacy_warmth", 2.0)
            reasons.append("相关关系记忆被召回")
        if "工作" in memory_text and "打扰" in memory_text and primary == "想念":
            labels.append("想念但克制")
            _add_delta(deltas, "arousal", -2.0)
            reasons.append("记忆中存在工作时克制打扰的边界")

        return EmotionAppraisalResult(
            primary_label=primary or "平静",
            compound_labels=_dedupe_labels(labels),
            deltas=deltas,
            confidence=confidence,
            reason="；".join(reasons),
            should_write_memory=confidence >= 0.8,
        )


class HeartLakeUpdater:
    """集中处理 HeartLake 的外部事件更新。"""

    # 默认情感评估规则列表
    DEFAULT_RULES: List[AppraisalRule] = []

    def __init__(
        self,
        heart_lake: HeartLake,
        custom_rules: Optional[List[AppraisalRule]] = None,
        emotion_appraiser: Optional[Union[EmotionAppraiser, "HybridEmotionAppraiser"]] = None,
    ) -> None:
        self.heart_lake = heart_lake
        self._jealousy_appraisal = _JealousyAppraisal()
        self._emotion_appraiser = emotion_appraiser or EmotionAppraiser()
        self._rules: List[AppraisalRule] = custom_rules or []

    def on_user_input(self, text: str, memory_summary: str = "") -> None:
        """根据用户输入更新情感状态。"""
        result = self._emotion_appraiser.appraise(
            text,
            self.heart_lake,
            memory_summary=memory_summary,
        )
        if result is None:
            return
        self.heart_lake.apply_emotion_delta(
            result.deltas,
            primary_label=result.primary_label,
            compound_labels=result.compound_labels,
            reason=result.reason,
            confidence=result.confidence,
        )

    def _evaluate_jealousy(self, text: str) -> None:
        """评估用户输入是否触发嫉妒情绪，应用评估结果。"""
        if not self._jealousy_appraisal.evaluate(
            text, self.heart_lake.security
        ):
            return

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


def _add_delta(deltas: Dict[str, float], key: str, value: float) -> None:
    deltas[key] = deltas.get(key, 0.0) + value


def _choose_primary(current: str, candidate: str, current_confidence: float, candidate_confidence: float) -> str:
    if not current:
        return candidate
    if candidate_confidence > current_confidence + 0.05:
        return candidate
    return current


def _dedupe_labels(labels: List[str]) -> List[str]:
    result: List[str] = []
    for label in labels:
        if label and label not in result:
            result.append(label)
    return result[:5]
