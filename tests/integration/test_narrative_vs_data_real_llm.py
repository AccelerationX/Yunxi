"""真实 LLM 对比测试：Narrative Prompt vs Data Prompt。

验证核心假设：叙事化 prompt 能让 LLM 自然生成更具"女友感"的回复，
减少对硬过滤和外部约束的依赖。
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
import requests

from core.cognition.heart_lake.core import HeartLake
from core.prompt_builder import PromptConfig, RuntimeContext, YunxiPromptBuilder
from domains.perception.coordinator import (
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
    SystemState,
)

pytestmark = [pytest.mark.real_llm]

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3:4b"


def _call_ollama(system_prompt: str, user_input: str, model: str = OLLAMA_MODEL) -> dict[str, Any]:
    """调用本地 Ollama，返回回复和元数据。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "stream": False,
        "options": {"temperature": 0.7},
    }
    start = time.time()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return {
            "content": content,
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "success": True,
        }
    except Exception as e:
        return {
            "content": f"ERROR: {e}",
            "elapsed_ms": round((time.time() - start) * 1000, 1),
            "success": False,
        }


# ------------------------------------------------------------------
# 场景定义
# ------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "深夜工作想念",
        "user_input": "在忙什么呢",
        "heart_lake": {
            "current_emotion": "想念",
            "miss_value": 75,
            "playfulness": 65,
            "vulnerability": 30,
            "intimacy_warmth": 70,
            "last_appraisal_reason": "远一下午没怎么找云汐说话了",
        },
        "perception": {
            "time": TimeContext(hour=23, readable_time="23:30"),
            "presence": UserPresence(
                focused_application="VS Code",
                foreground_process_name="Code.exe",
                activity_state="work",
                is_fullscreen=True,
                input_events_per_minute=16,
                idle_duration=0,
            ),
            "system": SystemState(cpu_percent=42),
        },
    },
    {
        "name": "游戏俏皮",
        "user_input": "你猜我在干嘛",
        "heart_lake": {
            "current_emotion": "开心",
            "miss_value": 30,
            "playfulness": 75,
            "vulnerability": 15,
            "intimacy_warmth": 65,
            "last_appraisal_reason": "远主动找云汐聊天",
        },
        "perception": {
            "time": TimeContext(hour=21, readable_time="21:00"),
            "presence": UserPresence(
                focused_application="Steam",
                foreground_process_name="steam.exe",
                activity_state="game",
                is_fullscreen=True,
                input_events_per_minute=5,
                idle_duration=0,
            ),
            "system": SystemState(cpu_percent=35),
        },
    },
    {
        "name": "空闲委屈",
        "user_input": "对不起刚才在开会",
        "heart_lake": {
            "current_emotion": "委屈",
            "miss_value": 60,
            "playfulness": 20,
            "vulnerability": 55,
            "intimacy_warmth": 55,
            "last_appraisal_reason": "远长时间未回复",
        },
        "perception": {
            "time": TimeContext(hour=15, readable_time="15:00"),
            "presence": UserPresence(
                focused_application="",
                activity_state="idle",
                is_fullscreen=False,
                input_events_per_minute=0,
                idle_duration=600,
            ),
            "system": SystemState(cpu_percent=10),
        },
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_narrative_vs_data_girlfriend_quality(scenario: dict, tmp_path: Any):
    """同一场景下，对比 narrative 和 data prompt 的 LLM 回复质量。"""
    # 构建 HeartLake
    hl = HeartLake()
    for key, val in scenario["heart_lake"].items():
        setattr(hl, key, val)

    # 构建 PerceptionSnapshot
    p = scenario["perception"]
    snapshot = PerceptionSnapshot(
        time_context=p["time"],
        user_presence=p["presence"],
        system_state=p["system"],
    )

    ctx = RuntimeContext(
        heart_lake_state=hl,
        perception_snapshot=snapshot,
        user_input=scenario["user_input"],
    )

    # 生成两种 prompt
    builder_narrative = YunxiPromptBuilder(PromptConfig(enable_narrative=True, enable_tools=False))
    prompt_narrative = builder_narrative.build_system_prompt(ctx)

    builder_data = YunxiPromptBuilder(PromptConfig(enable_narrative=False, enable_tools=False))
    prompt_data = builder_data.build_system_prompt(ctx)

    # 调用 LLM
    result_narrative = _call_ollama(prompt_narrative, scenario["user_input"])
    result_data = _call_ollama(prompt_data, scenario["user_input"])

    # 保存结果到日志目录
    log_dir = tmp_path.parent.parent / "narrative_llm_compare"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{scenario['name']}.json"
    # 同时保存到项目 logs 目录供人工审查
    project_log_dir = __import__("pathlib").Path("logs/narrative_llm_compare")
    project_log_dir.mkdir(parents=True, exist_ok=True)
    project_log_file = project_log_dir / f"{scenario['name']}.json"
    result_data_dict = {
        "scenario": scenario["name"],
        "user_input": scenario["user_input"],
        "prompt_narrative_length": len(prompt_narrative),
        "prompt_data_length": len(prompt_data),
        "narrative": result_narrative,
        "data": result_data,
    }
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(result_data_dict, f, ensure_ascii=False, indent=2)
    with open(project_log_file, "w", encoding="utf-8") as f:
        json.dump(result_data_dict, f, ensure_ascii=False, indent=2)

    # 断言：两者都应成功
    assert result_narrative["success"], f"Narrative LLM call failed: {result_narrative['content']}"
    assert result_data["success"], f"Data LLM call failed: {result_data['content']}"

    # 断言：回复不应为空
    assert result_narrative["content"].strip(), "Narrative response is empty"
    assert result_data["content"].strip(), "Data response is empty"

    # 断言：回复长度应在合理范围（女友式回复通常不长）
    narr_len = len(result_narrative["content"])
    data_len = len(result_data["content"])
    assert 5 < narr_len < 500, f"Narrative response length {narr_len} out of range"
    assert 5 < data_len < 500, f"Data response length {data_len} out of range"

    # 打印到 stdout 供人工审查
    print(f"\n{'='*60}")
    print(f"场景：{scenario['name']}")
    print(f"用户输入：{scenario['user_input']}")
    print(f"{'-'*30} NARRATIVE ({result_narrative['elapsed_ms']}ms) {'-'*30}")
    print(result_narrative["content"])
    print(f"{'-'*30} DATA ({result_data['elapsed_ms']}ms) {'-'*30}")
    print(result_data["content"])
    print(f"{'='*60}")
