from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from apps.daemon import main as daemon_main
from core.initiative.continuity import CompanionContinuityService
from domains.perception.coordinator import PerceptionSnapshot


class FakeLLM:
    async def complete(self, *args, **kwargs):
        return SimpleNamespace(content="在。")


class FakeMemory:
    def get_memory_summary(self, limit: int = 1) -> str:
        return ""

    async def close(self) -> None:
        return None


class FakeRuntime:
    def __init__(self) -> None:
        self.engine = SimpleNamespace(llm=FakeLLM())
        self.memory = FakeMemory()
        self.continuity = CompanionContinuityService()
        self.mcp_hub = None
        self.perception = SimpleNamespace(close=lambda: None)

    def get_context(self):
        return SimpleNamespace(
            mode="daily_mode",
            heart_lake_state=SimpleNamespace(current_emotion="平静", miss_value=0),
            perception_snapshot=PerceptionSnapshot(),
            available_tools=[],
        )


@pytest.mark.asyncio
async def test_deep_healthcheck_passes_with_fake_runtime(monkeypatch, tmp_path):
    events_path = tmp_path / "events.json"
    events_path.write_text(
        json.dumps([{"id": "event-1", "seed": "hello"}]),
        encoding="utf-8",
    )

    async def fake_build_runtime(config):
        return FakeRuntime()

    monkeypatch.setattr(daemon_main, "build_runtime", fake_build_runtime)

    report = await daemon_main.run_deep_healthcheck(
        daemon_main.DaemonConfig(
            initiative_event_library_path=str(events_path),
            continuity_state_path=str(tmp_path / "continuity.json"),
            enable_tool_use=False,
            initialize_desktop_mcp=False,
        )
    )

    assert report.status == "passed"
    steps = {step.name: step for step in report.steps}
    assert steps["llm_ping"].ok
    assert steps["event_library"].ok
    assert steps["continuity_rw"].ok
    assert steps["feishu_config"].detail == "disabled"


@pytest.mark.asyncio
async def test_deep_healthcheck_reports_missing_feishu_config(monkeypatch, tmp_path):
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps([{"id": "event-1"}]), encoding="utf-8")

    async def fake_build_runtime(config):
        return FakeRuntime()

    monkeypatch.setattr(daemon_main, "build_runtime", fake_build_runtime)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv("FEISHU_RECEIVER_ID", raising=False)

    report = await daemon_main.run_deep_healthcheck(
        daemon_main.DaemonConfig(
            initiative_event_library_path=str(events_path),
            continuity_state_path=str(tmp_path / "continuity.json"),
            enable_tool_use=False,
            initialize_desktop_mcp=False,
            feishu_enabled=True,
        )
    )

    assert report.status == "failed"
    feishu_step = next(step for step in report.steps if step.name == "feishu_config")
    assert not feishu_step.ok
    assert "FEISHU_APP_ID" in feishu_step.detail
