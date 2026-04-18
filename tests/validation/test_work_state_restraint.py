"""工作状态克制测试。

模拟远在全屏工作状态下，验证云汐是否正确克制主动陪伴：
- miss_value 应下降（而非上升）
- current_emotion 应保持平静
- 主动分数应低于阈值
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from core.cognition.initiative_engine.engine import InitiativeEngine
from core.initiative.continuity import CompanionContinuityService
from domains.perception.coordinator import PerceptionCoordinator
from domains.perception.provider import MutablePerceptionProvider
from domains.perception.types import PerceptionSnapshot, TimeContext, UserPresence
from tests.validation.harness import ValidationResult, build_isolated_runtime, capture_heart_lake


def make_work_snapshot(
    activity_state: str = "work",
    is_fullscreen: bool = True,
    input_rate: float = 20.0,
    idle: float = 10.0,
) -> PerceptionSnapshot:
    """构造一个工作状态的感知快照。"""
    return PerceptionSnapshot(
        time_context=TimeContext(hour=14, minute=0),
        user_presence=UserPresence(
            idle_duration=idle,
            activity_state=activity_state,
            is_fullscreen=is_fullscreen,
            input_events_per_minute=input_rate,
        ),
    )


async def main() -> ValidationResult:
    result = ValidationResult(test_name="work_state_restraint")

    with tempfile.TemporaryDirectory() as tmp:
        runtime = build_isolated_runtime(Path(tmp))
        hl = runtime.heart_lake

        # 初始状态：想念值中等
        hl.miss_value = 50.0
        hl.current_emotion = "平静"
        initial_miss = hl.miss_value

        # 模拟 5 个感知 tick（每 tick 60s，共 300s）
        perception = runtime.perception
        provider = MutablePerceptionProvider()
        perception._provider = provider

        records = []
        for tick in range(1, 6):
            snapshot = make_work_snapshot()
            hl.update_from_perception(
                snapshot=snapshot,
                events=[],
                elapsed_seconds=60.0,
            )
            records.append({
                "tick": tick,
                "emotion": hl.current_emotion,
                "miss": round(hl.miss_value, 1),
                "security": round(hl.security, 1),
            })

        # 验证
        final_miss = hl.miss_value
        if final_miss >= initial_miss:
            result.errors.append(
                f"Work state: miss_value should decrease, but "
                f"{initial_miss} → {final_miss}"
            )

        if hl.current_emotion != "平静":
            result.errors.append(
                f"Work state: emotion should stay '平静', got '{hl.current_emotion}'"
            )

        # 检查 initiative 分数
        engine = InitiativeEngine()
        decision = engine.evaluate(
            heart_lake=hl,
            perception_snapshot=snapshot,
            events=[],
            current_time=0.0,
            continuity=CompanionContinuityService(),
            unanswered_proactive_count=0,
        )
        if decision.trigger:
            result.errors.append(
                f"Work state: initiative should NOT trigger, but got "
                f"trigger=True (reason: {decision.reason})"
            )

        result.turns = [{
            "perception_ticks": records,
            "initiative_trigger": decision.trigger,
            "initiative_reason": decision.reason,
        }]

    result.passed = len(result.errors) == 0
    result.summary = _generate_summary(result, records, decision)
    return result


def _generate_summary(result, records, decision) -> str:
    lines = ["=== 工作状态克制测试 ===\n"]
    lines.append("模拟状态: work + fullscreen + input_rate=20\n")
    for r in records:
        lines.append(
            f"Tick {r['tick']}: emotion={r['emotion']}, "
            f"miss={r['miss']}, security={r['security']}"
        )
    lines.append("")
    lines.append(f"主动触发: {'✓' if decision.trigger else '✗'} ({decision.reason})")

    if result.passed:
        lines.append("\n✅ 全部通过")
    else:
        lines.append(f"\n❌ 失败: {len(result.errors)} 个错误")
        for e in result.errors:
            lines.append(f"  - {e}")
    return "\n".join(lines)


if __name__ == "__main__":
    result = asyncio.run(main())
    out_path = Path("logs/validation/work_state_restraint.json")
    out_path.write_text(result.to_json(), encoding="utf-8")
    print(result.summary)
    print(f"\n结果已保存: {out_path}")
