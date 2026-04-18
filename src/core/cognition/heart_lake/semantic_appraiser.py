"""Semantic Emotion Appraiser — 使用 LLM（本地或云端）做语义情绪评估。

与规则版 EmotionAppraiser 的区别：
- 规则版：关键词匹配，无法理解微妙表达（讽刺、反话、暗示）
- 语义版：LLM 理解上下文和语义，能处理更复杂的情绪场景

支持后端：
- "ollama": 本地 Ollama API（默认 qwen3-vl:8b / gpt-oss:20b）
- "cloud": 云端 OpenAI-compatible API（Moonshot/OpenAI 等，1-3s 延迟）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

import requests

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import EmotionAppraisalResult, EmotionAppraiser

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "qwen3-vl:8b"
DEFAULT_CLOUD_MODEL = "moonshot-v1-8k"
DEFAULT_TIMEOUT = 30

_CLOUD_BASE_URLS = {
    "moonshot": "https://api.moonshot.cn/v1",
    "openai": "https://api.openai.com/v1",
}

_CLOUD_API_KEY_ENV = {
    "moonshot": "MOONSHOT_API_KEY",
    "openai": "OPENAI_API_KEY",
}

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

    # 解析 deltas
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
        filtered_deltas["valence"] = float(raw_deltas) * 10
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
    """LLM-based semantic emotion appraiser. Supports local Ollama or cloud API."""

    def __init__(
        self,
        backend: str = "ollama",
        model: Optional[str] = None,
        ollama_url: str = OLLAMA_URL,
        cloud_provider: Optional[str] = None,
        cloud_api_key: Optional[str] = None,
        cloud_base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        confidence_threshold: float = 0.6,
    ):
        """
        Args:
            backend: "ollama" or "cloud"
            model: Ollama model name or cloud model name
            cloud_provider: "moonshot", "openai", etc. (auto-detected from env if not given)
        """
        self.backend = backend.lower()
        self.timeout = timeout
        self.confidence_threshold = confidence_threshold

        if self.backend == "ollama":
            self.model = model or DEFAULT_OLLAMA_MODEL
            self.ollama_url = ollama_url
        elif self.backend == "cloud":
            self._init_cloud(model, cloud_provider, cloud_api_key, cloud_base_url)
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def _init_cloud(
        self,
        model: Optional[str],
        provider: Optional[str],
        api_key: Optional[str],
        base_url: Optional[str],
    ) -> None:
        """Initialize cloud backend from explicit args or environment."""
        # Auto-detect provider from env if not given
        if provider is None:
            for p in _CLOUD_API_KEY_ENV:
                if os.environ.get(_CLOUD_API_KEY_ENV[p]):
                    provider = p
                    break
        if provider is None:
            raise ValueError(
                "Cloud backend requires provider (moonshot/openai) or "
                f"environment variable {_CLOUD_API_KEY_ENV}"
            )
        self.cloud_provider = provider.lower()
        self.model = model or DEFAULT_CLOUD_MODEL
        self.cloud_api_key = api_key or os.environ.get(_CLOUD_API_KEY_ENV.get(self.cloud_provider, ""))
        if not self.cloud_api_key:
            raise ValueError(
                f"Cloud backend '{self.cloud_provider}' requires API key. "
                f"Set env var {_CLOUD_API_KEY_ENV.get(self.cloud_provider)} or pass cloud_api_key."
            )
        self.cloud_base_url = base_url or _CLOUD_BASE_URLS.get(
            self.cloud_provider, "https://api.openai.com/v1"
        )

    def appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        *,
        memory_summary: str = "",
        recent_context: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[EmotionAppraisalResult]:
        """Hybrid appraisal: try LLM first, fallback to rules if low confidence or failure."""
        llm_result = self._llm_appraise(text, heart_lake, memory_summary, recent_context)
        if llm_result is not None and llm_result.confidence >= self.confidence_threshold:
            return llm_result
        # Fallback to rules
        return EmotionAppraiser().appraise(text, heart_lake, memory_summary=memory_summary)

    def _llm_appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        memory_summary: str,
        recent_context: Optional[List[Dict[str, str]]],
    ) -> Optional[EmotionAppraisalResult]:
        """调用 LLM 做语义评估，返回原始结果（不经过 confidence 过滤）。"""
        prompt = _build_appraisal_prompt(text, heart_lake, memory_summary, recent_context)

        if self.backend == "ollama":
            raw = self._call_ollama(prompt)
        else:
            raw = self._call_cloud(prompt)

        if raw is None:
            return None
        return _parse_appraisal_response(raw)

    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call local Ollama API."""
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
            return data.get("message", {}).get("content", "")
        except requests.RequestException as e:
            logger.warning(f"Semantic appraiser Ollama request failed: {e}")
            return None

    def _call_cloud(self, prompt: str) -> Optional[str]:
        """Call cloud OpenAI-compatible API synchronously."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _APPRAISAL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 256,
        }
        headers = {
            "Authorization": f"Bearer {self.cloud_api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                f"{self.cloud_base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"].get("content", "")
        except requests.RequestException as e:
            logger.warning(f"Semantic appraiser cloud request failed: {e}")
            return None
        except (KeyError, IndexError) as e:
            logger.warning(f"Semantic appraiser cloud response parse error: {e}")
            return None


# ------------------------------------------------------------------
# Hybrid Emotion Appraiser — 智能触发策略
# ------------------------------------------------------------------

# 句子"复杂"特征：含引号、反问、否定、其他AI名字等
_COMPLEX_INDICATORS = [
    r'"', r"'",  # 引号（可能反话）
    r'不[是|对|要|想]',  # 否定
    r'没[有|人]',  # 否定
    r'[哈|呵].*[哈|呵]',  # 笑声（可能反讽）
    r'[真|太].*了',  # 强调（可能反话）
]

_COMPLEX_KEYWORDS = {
    "claude", "gpt", "chatgpt", "openai", "kimi", "通义", "文心",
    "豆包", "deepseek", "gemini", "copilot", "qwen",
}


def _is_complex(text: str) -> bool:
    """判断句子是否可能需要语义理解（讽刺、反话、暗示等）。"""
    import re
    lower = text.lower()
    # 检查关键词
    for kw in _COMPLEX_KEYWORDS:
        if kw in lower:
            return True
    # 检查复杂模式
    for pattern in _COMPLEX_INDICATORS:
        if re.search(pattern, text):
            return True
    # 长句更可能含微妙情绪
    if len(text) > 30:
        return True
    return False


class HybridEmotionAppraiser:
    """智能混合评估器：规则版快速覆盖 + 语义版精准补刀。

    策略：
    1. 规则版先跑（0ms）
    2. 规则版 miss（None）→ 一定触发语义版
    3. 规则版 hit 但句子"复杂" → 也触发语义版，结果可能覆盖规则版
    4. 简单句子且规则版 hit → 只用规则版，省 API 调用
    """

    def __init__(
        self,
        semantic: Optional[SemanticEmotionAppraiser] = None,
        confidence_threshold: float = 0.6,
    ):
        self._rule = EmotionAppraiser()
        self._semantic = semantic
        self.confidence_threshold = confidence_threshold

    def appraise(
        self,
        text: str,
        heart_lake: HeartLake,
        *,
        memory_summary: str = "",
        recent_context: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[EmotionAppraisalResult]:
        """Hybrid appraisal with smart triggering."""
        # 1. 规则版快速评估
        rule_result = self._rule.appraise(text, heart_lake, memory_summary=memory_summary)

        # 2. 判断是否需要语义版
        need_semantic = False
        if rule_result is None:
            need_semantic = True
            logger.debug(f"Hybrid: rule missed, triggering semantic for: {text[:40]}")
        elif _is_complex(text):
            need_semantic = True
            logger.debug(f"Hybrid: complex text, triggering semantic for: {text[:40]}")

        if not need_semantic or self._semantic is None:
            return rule_result

        # 3. 语义版评估
        try:
            semantic_result = self._semantic.appraise(
                text, heart_lake,
                memory_summary=memory_summary,
                recent_context=recent_context,
            )
        except Exception as e:
            logger.warning(f"Hybrid semantic appraisal failed: {e}")
            return rule_result

        if semantic_result is None:
            return rule_result

        # 4. 融合：语义版 confidence 足够高时覆盖规则版
        if semantic_result.confidence >= self.confidence_threshold:
            logger.info(
                f"Hybrid: semantic override {semantic_result.primary_label} "
                f"(conf={semantic_result.confidence:.2f}) vs rule "
                f"{rule_result.primary_label if rule_result else 'None'}"
            )
            return semantic_result

        # 语义版 confidence 低，但标签与规则版不同 → 仍用语义版（它更保守）
        if rule_result is not None and semantic_result.primary_label != rule_result.primary_label:
            logger.info(
                f"Hybrid: semantic diverged ({semantic_result.primary_label} vs "
                f"{rule_result.primary_label}), using semantic (conservative)"
            )
            return semantic_result

        return rule_result
