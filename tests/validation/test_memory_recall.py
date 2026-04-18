"""记忆召回测试。

验证云汐的关系记忆是否正确进入 prompt：
1. 注入关系记忆（"远喜欢冰美式"、"上次去海边"）
2. 对话触发记忆召回
3. 检查 prompt 中是否包含记忆内容
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from core.prompt_builder import RuntimeContext
from tests.validation.harness import ValidationResult, build_isolated_runtime, run_chat_turn


SCRIPTED_RESPONSES = [
    "远不是要冰美式吗？云汐记得你喜欢不加糖的",
    "当然记得！上次去海边的时候...",
]


async def main() -> ValidationResult:
    result = ValidationResult(test_name="memory_recall")

    with tempfile.TemporaryDirectory() as tmp:
        runtime = build_isolated_runtime(
            Path(tmp),
            scripted_responses=SCRIPTED_RESPONSES,
        )

        # 注入关系记忆
        memory = runtime.memory
        memory.capture_relationship_memory("远", "远喜欢冰美式，不加糖")
        memory.capture_relationship_memory("远", "上次和远一起去海边，很开心")

        # 第一轮：触发记忆召回
        record1 = await run_chat_turn(
            runtime, "给我点杯喝的", turn=1, capture_prompt=True
        )
        result.turns.append(record1)

        prompt1 = record1.prompt_preview
        if "冰美式" not in prompt1 and "咖啡" not in prompt1:
            result.errors.append(
                "Round 1: '给我点杯喝的' should trigger '冰美式' memory in prompt"
            )

        # 第二轮：触发另一段记忆
        record2 = await run_chat_turn(
            runtime, "还记得上次出去玩吗", turn=2, capture_prompt=True
        )
        result.turns.append(record2)

        prompt2 = record2.prompt_preview
        if "海边" not in prompt2:
            result.errors.append(
                "Round 2: '还记得上次出去玩吗' should trigger '海边' memory in prompt"
            )

    result.passed = len(result.errors) == 0
    result.summary = _generate_summary(result)
    return result


def _generate_summary(result: ValidationResult) -> str:
    lines = ["=== 记忆召回测试 ===\n"]

    for record in result.turns:
        lines.append(f"输入: '{record.user_input}'")
        prompt = record.prompt_preview
        # 提取 memory section
        if "云汐的记忆" in prompt:
            start = prompt.find("云汐的记忆")
            end = prompt.find("\n\n", start)
            if end == -1:
                end = len(prompt)
            memory_section = prompt[start:end]
            lines.append(f"  Memory section:\n{memory_section[:300]}")
        else:
            lines.append("  未找到叙事化记忆 section")
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
    out_path = Path("logs/validation/memory_recall.json")
    out_path.write_text(result.to_json(), encoding="utf-8")
    print(result.summary)
    print(f"\n结果已保存: {out_path}")
