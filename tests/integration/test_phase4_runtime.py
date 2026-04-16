"""Phase 4 Runtime 行为回归测试。"""

import asyncio
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


class SlowCountingLLM:
    """Mock LLM that records whether runtime entries overlap."""

    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0
        self.call_count = 0
        self.history = []

    async def complete(self, system: str, messages: list, tools=None):
        self.call_count += 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        self.history.append({"system": system, "messages": messages, "tools": tools})
        try:
            await asyncio.sleep(0.02)
            return SlowCountingResponse(content=f"云汐串行回复 #{self.call_count}")
        finally:
            self.active_calls -= 1


class SlowCountingResponse:
    """Response object for SlowCountingLLM."""

    def __init__(self, content: str = "") -> None:
        self.content = content
        self.tool_calls = []


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
    assert "initiative_decision" in system_prompt
    assert "expression_context" in system_prompt
    assert "Yunxi wants to ask Yuan" in system_prompt
    assert "Do not copy it verbatim" in system_prompt


@pytest.mark.asyncio
async def test_proactive_event_affect_delta_updates_heart_lake_and_continuity(tmp_path):
    tester = YunxiConversationTester()
    tester.reset()
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "care_event_1",
                    "layer": "mixed",
                    "category": "care",
                    "seed": "Yunxi notices Yuan may be tired and wants to check in softly.",
                    "affect_delta": {"valence": -0.8, "arousal": 0.8},
                    "tags": ["care"],
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
    tester.set_heart_lake(emotion="想念", miss_value=95, security=80)
    tester.runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 23:30", hour=23),
            user_presence=UserPresence(idle_duration=360),
        )
    )
    tester.runtime.engine.llm.add_response("远，先停一下。我有点担心你。")

    proactive = await tester.runtime.proactive_tick()

    assert proactive is not None
    assert tester.runtime.heart_lake.current_emotion == "担心"
    assert tester.runtime.heart_lake.security < 80
    assert tester.runtime.continuity.initiative_events[-1].event_id == "care_event_1"


@pytest.mark.asyncio
async def test_runtime_serializes_concurrent_chat_entries():
    tester = YunxiConversationTester()
    tester.reset()
    slow_llm = SlowCountingLLM()
    tester.runtime.engine.llm = slow_llm

    responses = await asyncio.gather(
        tester.runtime.chat("第一条消息"),
        tester.runtime.chat("第二条消息"),
    )

    assert len(responses) == 2
    assert slow_llm.call_count == 2
    assert slow_llm.max_active_calls == 1


@pytest.mark.asyncio
async def test_runtime_serializes_chat_and_proactive_tick_entries():
    tester = YunxiConversationTester()
    tester.reset()
    slow_llm = SlowCountingLLM()
    tester.runtime.engine.llm = slow_llm
    tester.set_heart_lake(emotion="想念", miss_value=95)
    tester.runtime.perception.inject_snapshot(
        PerceptionSnapshot(
            time_context=TimeContext(readable_time="2026-04-16 23:30", hour=23),
            user_presence=UserPresence(
                focused_application="VS Code",
                idle_duration=360,
            ),
        )
    )

    proactive_task = asyncio.create_task(tester.runtime.proactive_tick())
    await asyncio.sleep(0)
    chat_task = asyncio.create_task(tester.runtime.chat("你在吗？"))
    proactive, chat_response = await asyncio.gather(proactive_task, chat_task)

    assert proactive is not None
    assert chat_response
    assert slow_llm.call_count == 2
    assert slow_llm.max_active_calls == 1
