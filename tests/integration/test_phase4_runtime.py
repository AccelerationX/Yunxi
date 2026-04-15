"""Phase 4 Runtime 行为回归测试。"""

import json
import random

import pytest

from core.initiative.event_system import ThreeLayerInitiativeEventSystem
from tests.integration.conversation_tester import YunxiConversationTester
from domains.perception.coordinator import (
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
)


@pytest.mark.asyncio
async def test_injected_perception_reaches_prompt():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_perception(
        user_presence=UserPresence(focused_application="VS Code", idle_duration=0)
    )
    tester.runtime.engine.llm.add_response("远又在 VS Code 里写代码啦？")

    await tester.talk("你看到我现在在干嘛吗？")
    system_prompt = tester.runtime.engine.llm.history[-1]["system"]

    assert "VS Code" in system_prompt


@pytest.mark.asyncio
async def test_continuity_reaches_prompt():
    tester = YunxiConversationTester()
    tester.reset()
    tester.runtime.continuity.add_open_thread(
        "ask Yuan about code progress",
        "Yuan was editing in VS Code",
    )
    tester.runtime.engine.llm.add_response("我记得刚才还想问你代码写得怎么样。")

    await tester.talk("你还记得刚才想聊什么吗？")
    system_prompt = tester.runtime.engine.llm.history[-1]["system"]

    assert "open_threads" in system_prompt
    assert "ask Yuan about code progress" in system_prompt


@pytest.mark.asyncio
async def test_proactive_tick_records_single_assistant_message():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="想念", miss_value=95)
    tester.runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 23:30", hour=23),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=360,
            ),
        )
    )
    tester.runtime.engine.llm.add_response("远～你还在写代码吗，我有点想你。")

    proactive = await tester.runtime.proactive_tick()

    assert proactive is not None
    assert len(tester.runtime.engine.context.messages) == 1


@pytest.mark.asyncio
async def test_proactive_tick_injects_life_event_material(tmp_path):
    tester = YunxiConversationTester()
    tester.reset()
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "coding_care_1",
                    "layer": "mixed",
                    "category": "care",
                    "seed": "Yunxi wants to ask Yuan whether he needs a short break from coding.",
                    "tags": ["care", "coding"],
                    "cooldown_seconds": 3600,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tester.runtime.initiative_event_system = ThreeLayerInitiativeEventSystem(
        library_path=library_path,
        state_path=tmp_path / "event_state.json",
        rng=random.Random(1),
    )
    tester.set_heart_lake(emotion="鎯冲康", miss_value=95)
    tester.runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-15 23:30", hour=23),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=360,
            ),
        )
    )
    tester.runtime.engine.llm.add_response("杩滐紝浣犺涓嶈鍏堟斁涓嬩唬鐮佷紤鎭竴涓嬶紵")

    proactive = await tester.runtime.proactive_tick()
    system_prompt = tester.runtime.engine.llm.history[-1]["system"]

    assert proactive is not None
    assert "initiative_event" in system_prompt
    assert "Yunxi wants to ask Yuan" in system_prompt
    assert "Do not copy it verbatim" in system_prompt
