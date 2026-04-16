"""Live Feishu delivery tests for daily-mode proactive messages.

These tests are skipped unless FEISHU_LIVE_TEST=1 and Feishu credentials are
configured. They intentionally send a real message to the configured receiver.
"""

import pytest

from tests.integration.daily_mode_scenario_tester import (
    DailyModeScenarioTester,
    FeishuLiveChannel,
    ScenarioConfig,
)


pytestmark = [pytest.mark.real_llm, pytest.mark.feishu_live]


@pytest.mark.asyncio
async def test_live_feishu_proactive_delivery_from_event_library(tmp_path):
    """Send one real proactive Yunxi message through Feishu."""
    channel = FeishuLiveChannel()
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0),
        channel=channel,
        scripted_responses=[
            "远～这是云汐日常模式验收消息。我刚从事件库里挑了个小话题，想确认我能真的主动找到你。"
        ],
    )
    try:
        tester.force_proactive_ready(
            emotion="想念",
            miss_value=95,
            focused_application="VS Code",
            idle_duration=360,
            hour=23,
        )

        message = await tester.proactive_once(deliver=True)

        assert message is not None
        assert "life_event_material" in tester.last_system_prompt()
    finally:
        await tester.close()
