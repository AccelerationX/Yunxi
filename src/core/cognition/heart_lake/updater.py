"""HeartLake 更新协调器。"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

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


class HeartLakeUpdater:
    """集中处理 HeartLake 的外部事件更新。"""

    # 默认情感评估规则列表
    DEFAULT_RULES: List[AppraisalRule] = []

    def __init__(
        self,
        heart_lake: HeartLake,
        custom_rules: Optional[List[AppraisalRule]] = None,
    ) -> None:
        self.heart_lake = heart_lake
        self._jealousy_appraisal = _JealousyAppraisal()
        self._rules: List[AppraisalRule] = custom_rules or []

    def on_user_input(self, text: str) -> None:
        """根据用户输入更新情感状态。"""
        self._evaluate_jealousy(text)

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
