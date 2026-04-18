"""综合报告生成器。

读取所有验证脚本的 JSON 结果，生成 markdown 报告。
"""

from __future__ import annotations

import json
from pathlib import Path

RESULT_FILES = [
    "logs/validation/conversation_flow.json",
    "logs/validation/sarcasm_detection.json",
    "logs/validation/work_state_restraint.json",
    "logs/validation/memory_recall.json",
]


def load_result(path: str):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def generate_report() -> str:
    lines = [
        "# 云汐日常模式 v2 真实使用验证报告",
        "",
        f"生成时间: {__import__('datetime').datetime.now().isoformat()}",
        "",
        "---",
        "",
    ]

    all_passed = True
    total_tests = 0
    passed_tests = 0

    for path in RESULT_FILES:
        result = load_result(path)
        if result is None:
            lines.append(f"## {Path(path).stem}")
            lines.append("⚠️ 结果文件不存在，请运行对应测试脚本")
            lines.append("")
            all_passed = False
            continue

        name = result.get("test_name", Path(path).stem)
        passed = result.get("passed", False)
        errors = result.get("errors", [])
        summary = result.get("summary", "")
        turns = result.get("turns", [])

        total_tests += 1
        if passed:
            passed_tests += 1
        else:
            all_passed = False

        status = "✅ 通过" if passed else "❌ 失败"
        lines.append(f"## {name} {status}")
        lines.append("")
        if errors:
            lines.append("**错误：**")
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

        # 情绪时间线
        if turns and isinstance(turns[0], dict) and "heart_lake_snapshot" in turns[0]:
            lines.append("**情绪变化时间线：**")
            lines.append("")
            lines.append("| Turn | 输入 | 情绪 | compound_labels | miss | security |")
            lines.append("|------|------|------|-----------------|------|----------|")
            for t in turns:
                after = t.get("heart_lake_snapshot", {}).get("after", {})
                lines.append(
                    f"| {t.get('turn', '?')} | "
                    f"{t.get('user_input', '')[:20]}... | "
                    f"{after.get('current_emotion', '-')} | "
                    f"{after.get('compound_labels', [])} | "
                    f"{after.get('miss_value', '-')} | "
                    f"{after.get('security', '-')} |"
                )
            lines.append("")
        elif turns and "perception_ticks" in turns[0]:
            lines.append("**感知 tick 记录：**")
            lines.append("")
            lines.append("| Tick | 情绪 | miss | security |")
            lines.append("|------|------|------|----------|")
            for tick in turns[0].get("perception_ticks", []):
                lines.append(
                    f"| {tick.get('tick')} | {tick.get('emotion')} | "
                    f"{tick.get('miss')} | {tick.get('security')} |"
                )
            lines.append("")

        # 详细摘要
        if summary:
            lines.append("**详细摘要：**")
            lines.append("```")
            lines.append(summary)
            lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**总计: {passed_tests}/{total_tests} 通过**")
    if all_passed:
        lines.append("🎉 所有测试通过！")
    else:
        lines.append("⚠️ 存在失败项，请查看详情。")

    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_report()
    out_path = Path("logs/validation/REPORT.md")
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n报告已保存: {out_path}")
