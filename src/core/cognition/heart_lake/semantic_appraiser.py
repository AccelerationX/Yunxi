"""Semantic Emotion Appraiser — 使用本地 LLM 做语义情绪评估。

与规则版 EmotionAppraiser 的区别：
- 规则版：关键词匹配，无法理解微妙表达（讽刺、反话、暗示）
- 语义版：LLM 理解上下文和语义，能处理更复杂的情绪场景

Hybrid 策略：
- LLM confidence >= 0.6 → 使用 LLM 结果
- LLM confidence < 0.6 或调用失败 → fallback 到规则版
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

import requests

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import EmotionAppraisalResult, EmotionAppraiser

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3-vl:8b"
DEFAULT_TIMEOUT = 30

# 评估 prompt 模板
_APPRAISAL_SYSTEM_PROMPT = (
    "你是一个情绪评估助手。根据用户输入，判断数字女友云汐应该有什么情绪变化。"
    "只输出 JSON，不要解释。"
)


_JSON_FORMAT_EXAMPLE = """输出格式（严格 JSON）：
{"primary_label":"开心","compound_labels":["安心"],"deltas":{"miss_value":0,"security":5,"trust":3},"confidence":0.8,"reason":"远说了暖心的话"}

primary_label 只能是：开心、想念、委屈、吃醋、担心、平静。
confidence 范围 0.0-1.0，普通对话给低值，明确情绪给高值。
deltas 范围 -15 到 +15。"""


def _build_appraisal_prompt(
    text: str,
    heart_lake: HeartLake,
    memory_summary: str,
    recent_context: Optional[List[Dict[str, str]]] = None,
) -> str:
    """构建发给 LLM 的评估 prompt。"""
    lines: List[str] = []

    lines.append("当前状态：")
    lines.append(f"情绪={heart_lake.current_emotion}, "
                 f"想念={heart_lake.miss_value:.0f}, "
                 f"安全={heart_lake.security:.0f}, "
                 f"俏皮={heart_lake.playfulness:.0f}, "
                 f"脆弱={heart_lake.vulnerability:.0f}")

    if memory_summary:
        lines.append(f"记忆：{memory_summary[:100]}")

    if recent_context:
        lines.append("最近对话：")
        for turn in recent_context[-2:]:
            role = turn.get("role", "")[:1]
            content = turn.get("content", "")[:40]
            lines.append(f"{role}:{content}")

    lines.append(f"用户说：{text}")
    lines.append(_JSON_FORMAT_EXAMPLE)

    return "\n".join(lines)


def _extract_json(raw: str) -> Optional[dict]:
    """从模型输出中提取 JSON 对象，处理 markdown code block 和多余文本。"""
    cleaned = raw.strip()

    # 1. 尝试直接解析
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 2. 尝试从 markdown code block 中提取
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', cleaned, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # 3. 尝试从文本中提取第一个 { ... } 对象
    m = re.search(r'\{[\s\S]*?\}', cleaned)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _parse_appraisal_response(raw: str) -> Optional[EmotionAppraisalResult]:
    """解析 LLM 返回的 JSON，转化为 EmotionAppraisalResult。"""
    data = _extract_json(raw)
    if data is None:
        logger.warning(f"Semantic appraiser no JSON found in: {raw[:200]}")
        return None

    primary = data.get("primary_label", "")
    compound = data.get("compound_labels", []) or []
    raw_deltas = data.get("deltas", {})
    confidence = float(data.get("confidence", 0.0))
    reason = data.get("reason", "")

    # 验证 primary_label（允许扩展标签，但给警告）
    valid_labels = {"开心", "想念", "委屈", "吃醋", "担心", "平静"}
    if primary not in valid_labels:
        logger.warning(f"Semantic appraiser unexpected primary_label: {primary}")
        # 不 reject，允许模型输出更细粒度的标签

    # 解析 deltas：可能是 dict、数字（旧格式兼容）、或缺失
    valid_dims = {
        "miss_value", "security", "possessiveness", "trust",
        "tenderness", "playfulness", "vulnerability", "intimacy_warmth",
        "valence", "arousal", "attachment",
    }
    filtered_deltas: Dict[str, float] = {}
    if isinstance(raw_deltas, dict):
        for key, val in raw_deltas.items():
            if key in valid_dims and isinstance(val, (int, float)):
                filtered_deltas[key] = float(val)
    elif isinstance(raw_deltas, (int, float)):
        # 旧格式兼容：单一数字映射到 valence
        filtered_deltas["valence"] = float(raw_deltas) * 10  # 缩放
        logger.debug(f"Semantic appraiser received scalar delta: {raw_deltas}")

    if not filtered_deltas and confidence > 0.3:
        logger.warning(f"Semantic appraiser returned confidence {confidence} but no valid deltas")

    return EmotionAppraisalResult(
        primary_label=primary,
        compound_labels=[c for c in compound if isinstance(c, str)],
        deltas=filtered_deltas,
        confidence=confidence,
        reason=reason,
        should_write_memory=confidence >= 0.8,
    )


class SemanticEmotionAppraiser:
    """LLM-based semantic emotion appraiser with rule fallback."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ollama_url: str = OLLAMA_URL,
        timeout: int = DEFAULT_TIMEOUT,
        confidence_threshold: float = 0.6,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout
        self.confidence_threshold = confidence_threshold
        self._rule_appraiser = EmotionAppraiser()

    def appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        *,
        memory_summary: str = "",
        recent_context: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[EmotionAppraisalResult]:
        """Hybrid appraisal: try LLM first, fallback to rules if low confidence or failure."""
        # 1. 尝试 LLM 语义评估
        llm_result = self._llm_appraise(text, heart_lake, memory_summary, recent_context)
        if llm_result is not None and llm_result.confidence >= self.confidence_threshold:
            logger.debug(
                f"Semantic appraisal used LLM result: {llm_result.primary_label} "
                f"(confidence={llm_result.confidence:.2f})"
            )
            return llm_result

        # 2. Fallback 到规则版
        if llm_result is not None:
            logger.debug(
                f"Semantic appraisal LLM confidence {llm_result.confidence:.2f} too low, "
                f"falling back to rules"
            )
        else:
            logger.debug("Semantic appraisal LLM failed, falling back to rules")

        rule_result = self._rule_appraiser.appraise(text, heart_lake, memory_summary=memory_summary)
        return rule_result

    def _llm_appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        memory_summary: str,
        recent_context: Optional[List[Dict[str, str]]],
    ) -> Optional[EmotionAppraisalResult]:
        """调用本地 Ollama 做语义评估。"""
        prompt = _build_appraisal_prompt(text, heart_lake, memory_summary, recent_context)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _APPRAISAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.3},
        }

        try:
            resp = requests.post(self.ollama_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            raw_content = data.get("message", {}).get("content", "")
            if not raw_content:
                return None
            return _parse_appraisal_response(raw_content)
        except requests.RequestException as e:
            logger.warning(f"Semantic appraiser Ollama request failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"Semantic appraiser unexpected error: {e}")
            return None
