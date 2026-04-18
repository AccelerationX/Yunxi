"""连续对话情绪过渡测试。

验证云汐在多轮对话中情绪是否正确过渡：
1. "今天好累" → 担心/温柔
2. "这个项目搞死我了" → 担心加深
3. "开玩笑的，其实还好" → 从担心转为平静/开心
4. "你最近好安静" → 想念
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root / "src"))

import harness


EXPECTED_TRANSITIONS = [
    {
        "input": "今天好累",
        "expected_emotions": {"担心", "平静"},
        "reason_keyword": "累",
    },
    {
        "input": "这个项目搞死我了",
        "expected_emotions": {"担心"},
        "reason_keyword": "崩溃",
    },
    {
        "input": "开玩笑的，其实还好",
        "expected_emotions": {"开心", "平静"},
        "reason_keyword": "",
    },
    {
        "input": "你最近好安静",
        "expected_emotions": {"想念", "担心"},
        "reason_keyword": "安静",
    },
]

SCRIPTED_RESPONSES = [
    "抱抱远～是不是加班太久了？",
    "天哪...那你要不要先休息一会儿？",
    "哼，吓我一跳！还好还好～",
    "啊...因为云汐一直在等远说话呀",
]


async def main() -> harness.ValidationResult:
    result = harness.ValidationResult(test_name="conversation_flow")

    with tempfile.TemporaryDirectory() as tmp:
        runtime = await harness.build_isolated_runtime(
            Path(tmp),
            scripted_responses=SCRIPTED_RESPONSES,
        )

        for i, turn_spec in enumerate(EXPECTED_TRANSITIONS, 1):
            record = await harness.run_chat_turn(
                runtime, turn_spec["input"], turn=i, capture_prompt=(i == 1)
            )
            result.turns.append(record)

            after = record.heart_lake_snapshot.get("after", {})
            actual_emotion = after.get("current_emotion", "")
            expected = turn_spec["expected_emotions"]

            if actual_emotion not in expected:
                result.errors.append(
                    f"Turn {i}: input='{turn_spec['input']}' "
                    f"expected {expected}, got '{actual_emotion}'"
                )

            compound = after.get("compound_labels", [])
            if i > 1:
                prev = result.turns[i - 2].heart_lake_snapshot.get("after", {}).get(
                    "current_emotion", ""
                )
                if prev != actual_emotion:
                    if not any("刚从" in c for c in compound):
                        result.errors.append(
                            f"Turn {i}: emotion changed {prev}→{actual_emotion} "
                            f"but no transition label in compound_labels"
                        )

    result.passed = len(result.errors) == 0
    result.summary = _generate_summary(result)
    return result


def _generate_summary(result: harness.ValidationResult) -> str:
    lines = ["=== 连续对话情绪过渡测试 ===\n"]
    for record in result.turns:
        before = record.heart_lake_snapshot.get("before", {})
        after = record.heart_lake_snapshot.get("after", {})
        lines.append(f"Turn {record.turn}: '{record.user_input}'")
        lines.append(
            f"  情绪: {before.get('current_emotion')} → {after.get('current_emotion')}"
        )
        lines.append(f"  compound: {after.get('compound_labels')}")
        lines.append(f"  miss: {before.get('miss_value')} → {after.get('miss_value')}")
        lines.append(f"  security: {before.get('security')} → {after.get('security')}")
        lines.append(f"  语义评估: {'✓' if record.semantic_appraisal_used else '✗'}")
        if record.errors:
            lines.append(f"  错误: {record.errors}")
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
    out_path = Path("logs/validation/conversation_flow.json")
    out_path.write_text(result.to_json(), encoding="utf-8")
    print(result.summary)
    print(f"\n结果已保存: {out_path}")
