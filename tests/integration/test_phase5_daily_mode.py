"""Phase 5 日常模式最小闭环测试。"""

import pytest

from apps.tray.web_server import build_runtime_status
from tests.integration.conversation_tester import YunxiConversationTester


@pytest.mark.asyncio
async def test_runtime_records_continuity_after_chat():
    tester = YunxiConversationTester()
    tester.reset()
    tester.runtime.engine.llm.add_response("远～我在呢")

    response = await tester.talk("你好")

    assert response == "远～我在呢"
    assert len(tester.runtime.continuity.exchanges) == 1
    assert tester.runtime.continuity.exchanges[0].user_message == "你好"
    assert "远～我在呢" in tester.runtime.continuity.get_summary()


@pytest.mark.asyncio
async def test_runtime_blocks_fourth_unanswered_proactive_message():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="想念", miss_value=95)
    tester.runtime.continuity.unanswered_proactive_count = 3

    proactive = await tester.runtime.proactive_tick()

    assert proactive is None


def test_tray_status_reflects_runtime_state():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="开心", miss_value=12)
    tester.runtime.continuity.record_exchange("你好", "远～")

    status = build_runtime_status(tester.runtime)

    assert status.mode == "daily_mode"
    assert status.emotion == "开心"
    assert status.miss_value == 12
    assert status.continuity_size == 1
