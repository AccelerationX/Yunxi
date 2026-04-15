"""Phase 4 Runtime 行为回归测试。"""

import pytest

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
