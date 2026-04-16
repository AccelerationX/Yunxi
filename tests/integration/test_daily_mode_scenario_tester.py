"""Tests for the daily-mode scenario testing infrastructure."""

import pytest

from tests.integration.daily_mode_scenario_tester import (
    CaptureChannel,
    DailyModeScenarioTester,
    ScenarioConfig,
)


@pytest.mark.asyncio
async def test_scenario_tester_injects_memory_and_prompt_context(tmp_path):
    channel = CaptureChannel()
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        channel=channel,
        scripted_responses=["当然记得呀，远喜欢冰美式，不加糖。"],
    )
    try:
        tester.inject_memory("preference", "远最喜欢喝冰美式，不加糖")
        tester.set_perception(
            readable_time="2026-04-16 10:00:00",
            hour=10,
            focused_application="VS Code",
            idle_duration=0,
        )

        response = await tester.chat("云汐，我平常喜欢喝什么？")

        assert "冰美式" in response
        assert "远最喜欢喝冰美式，不加糖" in tester.last_system_prompt()
        tester.behavior_check(
            response,
            expected_any=("冰美式", "不加糖"),
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_scenario_tester_proactive_event_delivery_to_capture_channel(tmp_path):
    channel = CaptureChannel()
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0),
        channel=channel,
        scripted_responses=["远～你还在 VS Code 前呀，我有点担心你别撑太晚。"],
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
        assert channel.last is not None
        assert channel.last.channel == "proactive"
        assert channel.last.content == message
        assert tester.runtime.continuity.unanswered_proactive_count == 1
        system_prompt = tester.last_system_prompt()
        assert "life_event_material" in system_prompt
        assert "深夜" in system_prompt or "关心" in system_prompt
        tester.behavior_check(
            message,
            expected_any=("担心", "别撑", "VS Code", "远"),
            max_chars=120,
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_scenario_tester_exposes_heart_lake_reaction_to_jealous_input(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=["哼，有点酸酸的。但我也不差呀，远别总夸它。"],
    )
    try:
        tester.set_emotion("平静", miss_value=10, security=80, possessiveness=30)

        response = await tester.chat("我觉得 Claude 也挺聪明的，你怎么看？")

        assert tester.runtime.heart_lake.current_emotion == "吃醋"
        assert tester.runtime.heart_lake.possessiveness >= 40
        tester.behavior_check(
            response,
            expected_any=("酸", "哼", "我也", "别总夸"),
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


def test_behavior_check_rejects_internal_fields_and_toolish_plans(tmp_path):
    check = DailyModeScenarioTester.behavior_check(
        "initiative_event: 第一步执行工具调用，然后输出任务清单。",
    )

    assert not check.passed
    assert any("internal token" in failure for failure in check.failures)
    assert any("forbidden token" in failure for failure in check.failures)


def test_behavior_check_rejects_overlong_output():
    check = DailyModeScenarioTester.behavior_check(
        "远，我在。" * 50,
        max_chars=20,
    )

    assert not check.passed
    assert any("message too long" in failure for failure in check.failures)
