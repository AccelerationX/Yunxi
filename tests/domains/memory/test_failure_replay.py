"""Phase 3: 失败回放（FailureReplay / MemoryManager 集成）测试。"""

import os
import tempfile

import pytest

from domains.memory.manager import MemoryManager
from domains.memory.skills.failure_replay import FailureReplay


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield tmpdir


class TestFailureReplay:
    def test_record_and_retrieve(self, temp_db_path):
        replay = FailureReplay(db_path=os.path.join(temp_db_path, "failures.db"))
        replay.record(
            intent_summary="查询天气失败",
            tool_name="weather_query",
            failure_reason="API 超时",
            suggestion="检查网络连接后再试",
            context_keywords=["天气", "查询"],
        )
        hints = replay.retrieve("查询北京天气", current_tools=["weather_query"])
        assert len(hints) == 1
        assert "检查网络" in hints[0]

    def test_retrieve_returns_empty_when_no_overlap(self, temp_db_path):
        replay = FailureReplay(db_path=os.path.join(temp_db_path, "failures.db"))
        replay.record(
            intent_summary="查询天气失败",
            tool_name="weather_query",
            failure_reason="API 超时",
            context_keywords=["天气"],
        )
        hints = replay.retrieve("打开计算器", current_tools=["calculator"])
        assert hints == []

    def test_clear_removes_all_records(self, temp_db_path):
        replay = FailureReplay(db_path=os.path.join(temp_db_path, "failures.db"))
        replay.record(intent_summary="失败", tool_name="t", failure_reason="r")
        replay.clear()
        hints = replay.retrieve("失败", current_tools=["t"])
        assert hints == []


class TestMemoryManagerFailureIntegration:
    @pytest.mark.asyncio
    async def test_record_experience_creates_failure_hint(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()

        mgr.record_experience(
            intent_text="查询天气失败",
            actions=[{"tool": "weather_query", "args": {}}],
            outcome="failure",
            source="mcp_audit",
            failure_reason="API 超时",
        )

        hints = mgr.get_failure_hints("查询北京天气", tools=["weather_query"])
        assert "API 超时" in hints

    @pytest.mark.asyncio
    async def test_get_failure_hints_format(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()
        mgr.add_failure_hint("不要重复调用截图")

        hints = mgr.get_failure_hints("截图")
        assert "不要重复调用截图" in hints
        assert hints.startswith("- 注意：")

    @pytest.mark.asyncio
    async def test_success_experience_does_not_create_failure(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()

        mgr.record_experience(
            intent_text="查询天气成功",
            actions=[{"tool": "weather_query", "args": {}}],
            outcome="success",
            source="mcp_audit",
        )

        hints = mgr.get_failure_hints("查询天气", tools=["weather_query"])
        assert hints == ""
