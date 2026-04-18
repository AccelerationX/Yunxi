"""SemanticEmotionAppraiser 单元测试（mock LLM 路径）。"""

import json

import pytest

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.semantic_appraiser import (
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
