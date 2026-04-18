"""运行所有验证脚本并生成报告。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

TESTS = [
    "tests/validation/test_conversation_flow.py",
    "tests/validation/test_sarcasm_detection.py",
    "tests/validation/test_work_state_restraint.py",
    "tests/validation/test_memory_recall.py",
]


def run_test(path: str) -> bool:
    """Run a single validation script."""
    print(f"\n{'='*60}")
    print(f"Running: {path}")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, path],
        cwd=Path(__file__).resolve().parent.parent.parent,
        capture_output=False,
    )
    return result.returncode == 0


async def main():
    print("🚀 云汐日常模式 v2 验证开始")
    print("模式: 脚本化 LLM（不消耗 API 额度）")
    print("如需真实 LLM 验证，设置 YUNXI_VALIDATION_PROVIDER=moonshot")

    results = []
    for test in TESTS:
        passed = run_test(test)
        results.append((test, passed))

    print(f"\n{'='*60}")
    print("生成综合报告...")
    print("=" * 60)
    subprocess.run([sys.executable, "tests/validation/generate_report.py"])

    print(f"\n{'='*60}")
    passed_count = sum(1 for _, p in results if p)
    print(f"结果: {passed_count}/{len(results)} 通过")
    for test, passed in results:
        status = "✅" if passed else "❌"
        print(f"  {status} {Path(test).stem}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
