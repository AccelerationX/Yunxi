"""Phase 5 日常模式最小闭环测试。"""

import pytest

from apps.tray.web_server import (
    build_control_panel_snapshot,
    build_runtime_status,
    create_status_app,
)
from domains.perception.coordinator import UserPresence
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
    tester.runtime.continuity.record_presence_murmur("云汐冒泡一下")
    tester.runtime.memory.skill_library.add_candidate(
        {
            "skill_name": "daily_candidate",
            "trigger_patterns": ["测试候选技能"],
            "parameters": [],
            "actions": [{"tool": "file_read", "args": {"path": "x"}}],
        },
        reason="phase5 status test",
    )
    tester.set_perception(
        user_presence=UserPresence(
            focused_application="Bilibili - Chrome",
            foreground_process_name="chrome.exe",
            is_fullscreen=True,
            input_events_per_minute=12,
        )
    )

    status = build_runtime_status(tester.runtime)

    assert status.mode == "daily_mode"
    assert status.emotion == "开心"
    assert status.miss_value == 12
    assert status.continuity_size == 1
    assert status.foreground_process_name == "chrome.exe"
    assert status.activity_state == "leisure"
    assert status.is_fullscreen is True
    assert status.input_events_per_minute == 12
    assert status.presence_murmur_count == 1
    assert status.recent_presence_murmurs == ["云汐冒泡一下"]
    assert status.skill_candidate_count == 1
    assert status.skill_candidates[0]["skill_name"] == "daily_candidate"
    assert status.daily_channel == "feishu"
    assert status.factory_entry_command == "yunxi"


def test_control_panel_snapshot_reads_logs(tmp_path):
    tester = YunxiConversationTester()
    tester.reset()
    log_path = tmp_path / "yunxi.log"
    log_path.write_text("line1\nline2\n", encoding="utf-8")

    snapshot = build_control_panel_snapshot(tester.runtime, [log_path], max_log_lines=1)

    assert snapshot.recent_logs == ["line2"]
    assert snapshot.factory_entry_command == "yunxi"


def test_status_app_exposes_control_panel_routes():
    tester = YunxiConversationTester()
    tester.reset()

    app = create_status_app(tester.runtime)
    route_paths = {route.resource.canonical for route in app.router.routes()}

    assert "/" in route_paths
    assert "/api/status" in route_paths
    assert "/api/logs" in route_paths
    assert "/api/factory-entry" in route_paths
    assert "/api/skills/candidates" in route_paths
    assert "/api/skills/approve" in route_paths
    assert "/api/skills/reject" in route_paths
