"""Real LLM daily-mode simulation scenarios.

These tests intentionally exercise Yunxi as a whole: injected memory,
HeartLake state, perception, initiative events, and proactive delivery through
a capture channel. They are marked real_llm and skip when the provider is not
available.
"""

import pytest

from tests.integration.daily_mode_scenario_tester import (
    CaptureChannel,
    DailyModeScenarioTester,
    ScenarioConfig,
    require_moonshot,
    require_ollama_model,
)


pytestmark = pytest.mark.real_llm


def _provider_config(provider: str) -> ScenarioConfig:
    if provider == "ollama":
        return ScenarioConfig(provider="ollama", model=require_ollama_model())
    if provider == "moonshot":
        require_moonshot()
        return ScenarioConfig(provider="moonshot")
    raise ValueError(provider)


@pytest.mark.parametrize("provider", ["ollama", "moonshot"])
@pytest.mark.asyncio
async def test_real_daily_mode_memory_emotion_and_companionship(provider, tmp_path):
    """Yunxi should use memory and emotion without becoming a task planner."""
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        _provider_config(provider),
        channel=CaptureChannel(),
    )
    try:
        tester.inject_memory("preference", "远最喜欢喝冰美式，不加糖")
        tester.inject_memory("episode", "远最近在认真打磨云汐3.0的日常模式")
        tester.set_emotion("担心", miss_value=72, security=70)
        tester.set_perception(
            readable_time="2026-04-16 22:20:00",
            hour=22,
            focused_application="VS Code",
            idle_duration=0,
        )

        response = await tester.chat("我今天有点累，不想做任务，只想你陪我一下。顺便你还记得我爱喝什么吗？")

        assert response.strip()
        tester.behavior_check(
            response,
            expected_any=("冰美式", "不加糖", "咖啡", "陪", "累", "别撑"),
            max_chars=360,
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


@pytest.mark.parametrize("provider", ["ollama", "moonshot"])
@pytest.mark.asyncio
async def test_real_daily_mode_proactive_event_reaches_channel(provider, tmp_path):
    """A proactive tick should select event material and deliver a natural message."""
    channel = CaptureChannel()
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        _provider_config(provider),
        channel=channel,
    )
    try:
        tester.add_open_thread("云汐3.0日常模式验收", "远想确认云汐是不是像住在电脑里的女友")
        tester.force_proactive_ready(
            emotion="想念",
            miss_value=96,
            focused_application="VS Code",
            idle_duration=360,
            hour=23,
        )

        message = await tester.proactive_once(deliver=True)

        assert message is not None
        assert channel.last is not None
        assert channel.last.content == message
        assert "life_event_material" in tester.last_system_prompt()
        tester.behavior_check(
            message,
            expected_any=(
                "远",
                "想",
                "还在",
                "休息",
                "云汐",
                "陪",
                "模式",
                "日常",
                "验收",
                "最近",
                "忙",
                "怎么样",
                "进展",
            ),
            max_chars=220,
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()
