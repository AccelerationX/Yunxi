"""SemanticEmotionAppraiser 单元测试（mock LLM 路径）。"""

import json

import pytest

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.semantic_appraiser import (
    HybridEmotionAppraiser,
    SemanticEmotionAppraiser,
    _build_appraisal_prompt,
    _parse_appraisal_response,
)


# ------------------------------------------------------------------
# _build_appraisal_prompt
# ------------------------------------------------------------------

def test_build_prompt_includes_heart_lake_state():
    hl = HeartLake()
    hl.current_emotion = "想念"
    hl.miss_value = 75
    prompt = _build_appraisal_prompt("在忙什么呢", hl, "", None)
    assert "想念" in prompt
    assert "想念=75" in prompt
    assert "在忙什么呢" in prompt


def test_build_prompt_includes_memory_and_context():
    hl = HeartLake()
    prompt = _build_appraisal_prompt(
        "你好",
        hl,
        memory_summary="远喜欢冰美式",
        recent_context=[{"role": "user", "content": "早"}, {"role": "assistant", "content": "早呀～"}],
    )
    assert "远喜欢冰美式" in prompt
    assert "早呀～" in prompt


# ------------------------------------------------------------------
# _parse_appraisal_response
# ------------------------------------------------------------------

def test_parse_valid_json():
    raw = json.dumps({
        "primary_label": "想念",
        "compound_labels": ["想念但不打扰"],
        "deltas": {"miss_value": 8, "security": -2},
        "confidence": 0.82,
        "reason": "远一下午没理云汐了",
    })
    result = _parse_appraisal_response(raw)
    assert result is not None
    assert result.primary_label == "想念"
    assert "想念但不打扰" in result.compound_labels
    assert result.deltas["miss_value"] == 8.0
    assert result.confidence == 0.82
    assert result.should_write_memory is True


def test_parse_strips_markdown_code_block():
    raw = "```json\n" + json.dumps({
        "primary_label": "开心",
        "compound_labels": [],
        "deltas": {"playfulness": 5},
        "confidence": 0.75,
        "reason": "远主动找云汐聊天",
    }) + "\n```"
    result = _parse_appraisal_response(raw)
    assert result is not None
    assert result.primary_label == "开心"


def test_parse_invalid_label_is_accepted_with_warning():
    """不在白名单的标签不再被 reject，而是接受并记录 warning。"""
    raw = json.dumps({
        "primary_label": "愤怒",  # 不在允许列表中
        "deltas": {},
        "confidence": 0.9,
        "reason": "",
    })
    result = _parse_appraisal_response(raw)
    assert result is not None
    assert result.primary_label == "愤怒"
    assert result.confidence == 0.9


def test_parse_invalid_json_returns_none():
    result = _parse_appraisal_response("not json at all")
    assert result is None


def test_parse_filters_invalid_delta_keys():
    raw = json.dumps({
        "primary_label": "平静",
        "deltas": {"miss_value": 5, "invalid_key": 999, "security": -3},
        "confidence": 0.5,
        "reason": "普通寒暄",
    })
    result = _parse_appraisal_response(raw)
    assert result is not None
    assert "miss_value" in result.deltas
    assert "security" in result.deltas
    assert "invalid_key" not in result.deltas


# ------------------------------------------------------------------
# SemanticEmotionAppraiser hybrid logic
# ------------------------------------------------------------------

def test_high_confidence_llm_result_used():
    """LLM confidence >= threshold → 使用 LLM 结果，不走规则。"""
    appraiser = SemanticEmotionAppraiser(confidence_threshold=0.6)
    # mock LLM 返回高 confidence
    llm_result = _parse_appraisal_response(json.dumps({
        "primary_label": "担心",
        "compound_labels": ["心疼"],
        "deltas": {"tenderness": 10},
        "confidence": 0.85,
        "reason": "远说自己好累",
    }))
    appraiser._llm_appraise = lambda *args, **kwargs: llm_result

    hl = HeartLake()
    result = appraiser.appraise("我好累", hl)
    assert result is not None
    assert result.primary_label == "担心"
    assert result.confidence == 0.85


def test_low_confidence_falls_back_to_rules():
    """LLM confidence < threshold → fallback 到规则版。"""
    appraiser = SemanticEmotionAppraiser(confidence_threshold=0.6)
    # mock LLM 返回低 confidence
    llm_result = _parse_appraisal_response(json.dumps({
        "primary_label": "平静",
        "deltas": {},
        "confidence": 0.3,
        "reason": "普通回复",
    }))
    appraiser._llm_appraise = lambda *args, **kwargs: llm_result

    hl = HeartLake()
    # "累" 是规则版的触发词
    result = appraiser.appraise("我好累", hl)
    assert result is not None
    # 应该 fallback 到规则版，规则版会识别"累"并给出担心+温柔
    assert result.primary_label == "担心"
    assert result.confidence >= 0.6  # 规则版 confidence


def test_llm_failure_falls_back_to_rules():
    """LLM 调用失败 → fallback 到规则版。"""
    appraiser = SemanticEmotionAppraiser()
    appraiser._llm_appraise = lambda *args, **kwargs: None

    hl = HeartLake()
    result = appraiser.appraise("我好累", hl)
    assert result is not None
    assert result.primary_label == "担心"


# ------------------------------------------------------------------
# HybridEmotionAppraiser 智能触发策略
# ------------------------------------------------------------------

def test_hybrid_triggers_semantic_when_rule_misses():
    """规则版 miss → Hybrid 触发语义版。"""
    semantic = SemanticEmotionAppraiser()
    # mock 语义版返回高 confidence 结果
    mock_result = _parse_appraisal_response(json.dumps({
        "primary_label": "委屈",
        "deltas": {"miss_value": 5},
        "confidence": 0.85,
        "reason": "反话",
    }))
    semantic._llm_appraise = lambda *args, **kwargs: mock_result

    hybrid = HybridEmotionAppraiser(semantic=semantic)
    hl = HeartLake()
    # "你真好，都不理我了" 规则版无法识别（无关键词）
    result = hybrid.appraise("你真好，都不理我了", hl)
    assert result is not None
    assert result.primary_label == "委屈"


def test_hybrid_uses_rule_only_for_simple_text():
    """简单句子 + 规则版 hit → 不触发语义版，省 API 调用。"""
    semantic = SemanticEmotionAppraiser()
    # 如果语义版被调用，这个 mock 会返回特殊标签
    semantic._llm_appraise = lambda *args, **kwargs: _parse_appraisal_response(
        json.dumps({"primary_label": " semantic_triggered ", "deltas": {}, "confidence": 0.99})
    )

    hybrid = HybridEmotionAppraiser(semantic=semantic)
    hl = HeartLake()
    # "我好累" 规则版能识别，且句子简单
    result = hybrid.appraise("我好累", hl)
    assert result is not None
    # 应该走规则版，没有触发语义版
    assert result.primary_label == "担心"


def test_hybrid_triggers_semantic_for_complex_text():
    """复杂句子（含引号/其他AI名）→ 即使规则版 hit 也触发语义版。"""
    semantic = SemanticEmotionAppraiser()
    mock_result = _parse_appraisal_response(json.dumps({
        "primary_label": "吃醋",
        "deltas": {"security": -5},
        "confidence": 0.80,
        "reason": "提到 Claude",
    }))
    semantic._llm_appraise = lambda *args, **kwargs: mock_result

    hybrid = HybridEmotionAppraiser(semantic=semantic)
    hl = HeartLake()
    result = hybrid.appraise("Claude 回答得真好", hl)
    assert result is not None
    assert result.primary_label == "吃醋"


def test_hybrid_fallback_to_rule_when_semantic_fails():
    """语义版调用失败 → fallback 到规则版。"""
    semantic = SemanticEmotionAppraiser()
    semantic._llm_appraise = lambda *args, **kwargs: None

    hybrid = HybridEmotionAppraiser(semantic=semantic)
    hl = HeartLake()
    result = hybrid.appraise("我好累", hl)
    assert result is not None
    assert result.primary_label == "担心"


def test_hybrid_uses_semantic_when_diverged():
    """语义版结果与规则版不同且 confidence 低于阈值 → 仍用语义版（更保守）。"""
    semantic = SemanticEmotionAppraiser(confidence_threshold=0.0)
    # 语义版：委屈，confidence 0.50（SemanticEmotionAppraiser threshold=0 所以不过滤）
    mock_result = _parse_appraisal_response(json.dumps({
        "primary_label": "委屈",
        "deltas": {"miss_value": 3},
        "confidence": 0.50,
        "reason": "可能委屈",
    }))
    semantic._llm_appraise = lambda *args, **kwargs: mock_result

    hybrid = HybridEmotionAppraiser(semantic=semantic, confidence_threshold=0.6)
    hl = HeartLake()
    # "我好累啊Claude" 含"Claude"→复杂模式→语义版被调用
    # 规则版识别"累" → 担心；语义版 mock → 委屈
    result = hybrid.appraise("我好累啊Claude", hl)
    assert result is not None
    # 规则版和语义版标签不同，语义版更保守，使用语义版
    assert result.primary_label == "委屈"
