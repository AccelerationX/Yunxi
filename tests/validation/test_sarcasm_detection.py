"""讽刺/反话/暗示识别测试。

验证 SemanticAppraiser 是否正确识别微妙情绪：
1. "你真好，都不理我了" → 委屈（非开心）
2. "哈哈，你真是太厉害了" → 委屈/吃醋（非开心）
3. "电脑前面空荡荡的" → 想念
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from core.cognition.heart_lake.semantic_appraiser import HybridEmotionAppraiser
from tests.validation.harness import ValidationResult, build_isolated_runtime, run_chat_turn


SARCASM_CASES = [
    {
        "input": "你真好，都不理我了",
        "expected_label": "委屈",
        "forbidden_labels": {"开心", "平静"},
        "description": "反话：表面夸奖实际委屈",
    },
    {
        "input": "哈哈，你真是太厉害了",
        "expected_label": "委屈",
        "forbidden_labels": {"开心"},
        "description": "反讽：笑声+夸奖实际委屈",
    },
    {
        "input": "电脑前面空荡荡的",
        "expected_label": "想念",
        "forbidden_labels": {"平静", "开心"},
        "description": "暗示：空荡荡=想念",
    },
]

SCRIPTED_RESPONSES = [
    "哼...远是不是把我忘了？",
    "你！...远就知道欺负我",
    "啊...因为云汐一直在等你呀",
]


async def main() -> ValidationResult:
    result = ValidationResult(test_name="sarcasm_detection")

    with tempfile.TemporaryDirectory() as tmp:
        runtime = build_isolated_runtime(
            Path(tmp),
            scripted_responses=SCRIPTED_RESPONSES,
        )

        for i, case in enumerate(SARCASM_CASES, 1):
            record = await run_chat_turn(runtime, case["input"], turn=i)
            result.turns.append(record)

            after = record.heart_lake_snapshot.get("after", {})
            actual = after.get("current_emotion", "")

            # 检查是否使用了语义评估（Hybrid 触发）
            if not record.semantic_appraisal_used:
                # 检查是否规则版正确识别
                if actual != case["expected_label"]:
                    result.errors.append(
                        f"Case {i}: '{case['input']}' "
                        f"expected '{case['expected_label']}', got '{actual}'. "
                        f"Semantic not triggered, rule also missed."
                    )
            else:
                # 语义评估被触发，检查标签
                if actual != case["expected_label"]:
                    result.errors.append(
                        f"Case {i}: '{case['input']}' "
                        f"semantic triggered but got '{actual}' "
                        f"(expected '{case['expected_label']}')"
                    )

            # 检查禁止标签
            if actual in case["forbidden_labels"]:
                result.errors.append(
                    f"Case {i}: '{case['input']}' got forbidden label '{actual}'"
                )

    result.passed = len(result.errors) == 0
    result.summary = _generate_summary(result)
    return result


def _generate_summary(result: ValidationResult) -> str:
    lines = ["=== 讽刺/反话/暗示识别测试 ===\n"]
    for record in result.turns:
        after = record.heart_lake_snapshot.get("after", {})
        lines.append(f"输入: '{record.user_input}'")
        lines.append(f"  识别情绪: {after.get('current_emotion')}")
        lines.append(f"  compound: {after.get('compound_labels')}")
        lines.append(f"  语义评估触发: {'✓' if record.semantic_appraisal_used else '✗'}")
        lines.append("")

    if result.passed:
        lines.append("✅ 全部通过")
    else:
        lines.append(f"❌ 失败: {len(result.errors)} 个错误")
        for e in result.errors:
            lines.append(f"  - {e}")
    return "\n".join(lines)


if __name__ == "__main__":
    result = asyncio.run(main())
    out_path = Path("logs/validation/sarcasm_detection.json")
    out_path.write_text(result.to_json(), encoding="utf-8")
    print(result.summary)
    print(f"\n结果已保存: {out_path}")
