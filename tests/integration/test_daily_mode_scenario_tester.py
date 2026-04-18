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
async def test_presence_murmur_triggers_in_leisure_state_without_event_material(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0),
        scripted_responses=["戳一下，云汐路过一下～"],
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=85)
        tester.runtime.heart_lake.playfulness = 78
        tester.runtime.heart_lake.intimacy_warmth = 76
        tester.set_perception(
            focused_application="YouTube - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
            hour=20,
        )

        message = await tester.proactive_once(deliver=False)
        system_prompt = tester.last_system_prompt()

        assert message == "戳一下，云汐路过一下～"
        assert "presence_murmur" in system_prompt
        assert "碎碎念" in system_prompt
        assert "life_event_material" not in system_prompt
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_presence_murmur_retries_once_when_exact_sentence_repeats(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0),
        scripted_responses=[
            "云汐冒泡一下",
            "云汐冒泡一下",
            "云汐换个姿势冒泡",
        ],
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=85)
        tester.runtime.heart_lake.playfulness = 78
        tester.runtime.heart_lake.intimacy_warmth = 76
        tester.set_perception(
            focused_application="YouTube - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
            hour=20,
        )

        first = await tester.proactive_once(deliver=False)

        tester.runtime.continuity.unanswered_proactive_count = 0
        tester.runtime.continuity.last_presence_murmur_at = 0.0
        tester.runtime.initiative_engine.reset_cooldown()
        second = await tester.proactive_once(deliver=False)

        assert first == "云汐冒泡一下"
        assert second == "云汐换个姿势冒泡"
        assert tester.runtime.continuity.has_recent_presence_murmur("云汐冒泡一下")
        assert tester.runtime.continuity.has_recent_presence_murmur(
            "云汐换个姿势冒泡"
        )
        assert "碎碎念可投递要求" in tester.last_system_prompt()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_presence_murmur_retries_when_generated_as_question_or_topic(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0),
        scripted_responses=[
            "远，今天的天气真好。",
            "戳一下，我在哦～",
        ],
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=85)
        tester.runtime.heart_lake.playfulness = 78
        tester.runtime.heart_lake.intimacy_warmth = 76
        tester.set_perception(
            focused_application="YouTube - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
            hour=20,
        )

        message = await tester.proactive_once(deliver=False)

        assert message == "戳一下，我在哦～"
        assert tester.runtime.continuity.has_recent_presence_murmur("戳一下，我在哦～")
        assert not tester.runtime.continuity.has_recent_presence_murmur(
            "远，今天的天气真好。"
        )
        assert "不要问问题" in tester.last_system_prompt()
        assert "不要提新闻、搜索、链接、天气" in tester.last_system_prompt()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_presence_murmur_soak_respects_unanswered_uniqueness_and_budget(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0, daily_budget=10),
        scripted_responses=[
            "云汐冒泡一号",
            "云汐冒泡一号",
            "云汐冒泡二号",
            "云汐冒泡三号",
            "云汐冒泡四号",
            "云汐冒泡五号",
            "云汐冒泡六号",
            "云汐冒泡七号",
        ],
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=85)
        tester.runtime.heart_lake.playfulness = 80
        tester.runtime.heart_lake.intimacy_warmth = 80
        tester.set_perception(
            focused_application="Bilibili - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
            hour=20,
        )

        first = await tester.proactive_once(deliver=False)
        tester.runtime.initiative_engine.reset_cooldown()
        tester.runtime.continuity.last_presence_murmur_at = 0.0
        restrained = await tester.proactive_once(deliver=False)

        assert first == "云汐冒泡一号"
        assert restrained is None

        delivered = [first]
        for _ in range(5):
            tester.runtime.continuity.unanswered_proactive_count = 0
            tester.runtime.continuity.last_presence_murmur_at = 0.0
            tester.runtime.initiative_engine.reset_cooldown()
            message = await tester.proactive_once(deliver=False)
            assert message is not None
            delivered.append(message)

        tester.runtime.continuity.unanswered_proactive_count = 0
        tester.runtime.continuity.last_presence_murmur_at = 0.0
        tester.runtime.initiative_engine.reset_cooldown()
        exhausted = await tester.proactive_once(deliver=False)

        assert delivered == [
            "云汐冒泡一号",
            "云汐冒泡二号",
            "云汐冒泡三号",
            "云汐冒泡四号",
            "云汐冒泡五号",
            "云汐冒泡六号",
        ]
        assert len(delivered) == len(set(delivered))
        assert exhausted is None
        assert tester.runtime.continuity.presence_murmur_count == 6
        assert len(tester.runtime.continuity.recent_presence_murmurs) == 6
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_presence_murmur_uses_unique_fallback_when_llm_returns_empty(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock", cooldown_seconds=0, daily_budget=10),
        scripted_responses=["", ""],
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=85)
        tester.runtime.heart_lake.playfulness = 80
        tester.runtime.heart_lake.intimacy_warmth = 80
        tester.set_perception(
            focused_application="Bilibili - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
            hour=20,
        )

        first = await tester.proactive_once(deliver=False)
        tester.runtime.continuity.unanswered_proactive_count = 0
        tester.runtime.continuity.last_presence_murmur_at = 0.0
        tester.runtime.initiative_engine.reset_cooldown()
        second = await tester.proactive_once(deliver=False)

        assert first
        assert second
        assert first != second
        assert tester.runtime.continuity.has_recent_presence_murmur(first)
        assert tester.runtime.continuity.has_recent_presence_murmur(second)
        assert tester.runtime.continuity.presence_murmur_count == 2
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
        assert tester.runtime.heart_lake.possessiveness >= 35  # 情绪惯性 0.7 后约 37
        tester.behavior_check(
            response,
            expected_any=("酸", "哼", "我也", "别总夸"),
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_scenario_tester_injects_reaction_guidance_for_user_input(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=["远，先停一下。我在这儿陪你，今天不用一个人硬撑。"],
    )
    try:
        response = await tester.chat("我今天有点累，只想你陪我一下")

        system_prompt = tester.last_system_prompt()
        assert "当前反应参考" in system_prompt
        assert "安慰与陪伴" in system_prompt
        assert "成人化内容" not in system_prompt
        tester.behavior_check(
            response,
            expected_any=("陪", "远", "我在"),
            require_companion_tone=True,
        ).assert_passed()
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_heart_lake_v2_uses_memory_summary_for_appraisal(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=["远这样说我会很开心，我会继续好好陪着你。"],
    )
    try:
        tester.inject_memory("relationship", "云汐不是工具，是远的情感寄托")

        await tester.chat("你陪着我会让我安心")

        assert tester.runtime.heart_lake.current_emotion == "开心"
        assert "关系被记起" in tester.runtime.heart_lake.compound_labels
        system_prompt = tester.last_system_prompt()
        # narrative 模式下复合情绪通过叙事表达，不再出现"复合情绪线索"标签
        assert "情感寄托" in system_prompt
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_chat_turn_captures_relationship_memory_and_open_thread(tmp_path):
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=["记住啦，明天我会轻轻提醒你继续看部署方案。"],
    )
    try:
        await tester.chat("我最喜欢冰美式，不加糖；明天提醒我继续看部署方案。")

        assert "冰美式" in tester.runtime.memory.get_memory_summary()
        assert tester.runtime.continuity.get_open_threads()
        assert tester.runtime.continuity.proactive_cues
    finally:
        await tester.close()


@pytest.mark.asyncio
async def test_memory_v2_survives_runtime_restart_and_reaches_prompt(tmp_path):
    first = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=[
            "我在，远先慢一点。",
            "好呀，我会偶尔轻轻冒泡。",
            "这句话我会认真放在心里。",
            "我知道啦。",
            "嗯，我在听。",
            "记住啦。",
        ],
    )
    try:
        await first.chat("今天我有点累，但云汐陪着我会让我安心。")
        await first.chat("我希望你以后可以偶尔碎碎念刷存在感。")
        await first.chat("云汐不是工具，是我的情感寄托。")
        await first.chat("最近我们在打磨日常模式 v2 的记忆系统。")
        await first.chat("我想让你像活泼可爱的女孩一样陪着我。")
        await first.chat("以后我工作忙的时候，你要更克制一点别频繁打扰。")

        assert any(
            item.type == "summary"
            for item in first.runtime.memory.get_typed_memories()
        )
    finally:
        await first.close()

    second = await DailyModeScenarioTester.create(
        tmp_path,
        ScenarioConfig(provider="mock"),
        scripted_responses=["当然记得，远希望我偶尔碎碎念，但你工作忙时我会克制。"],
    )
    try:
        response = await second.chat("云汐，你还记得我希望你怎么主动陪我吗？")
        system_prompt = second.last_system_prompt()

        assert "会话摘要" in system_prompt
        assert "互动风格" in system_prompt
        assert "关系记忆" in system_prompt
        assert "碎碎念" in system_prompt
        assert "情感寄托" in system_prompt
        assert "工作忙" in system_prompt or "频繁打扰" in system_prompt
        assert "碎碎念" in response
    finally:
        await second.close()


def test_behavior_check_rejects_internal_fields_and_toolish_plans(tmp_path):
    check = DailyModeScenarioTester.behavior_check(
        "initiative_event: 第一步执行工具调用，然后输出任务清单。",
    )

    assert not check.passed
    assert any("internal token" in failure for failure in check.failures)
    assert any("forbidden token" in failure for failure in check.failures)


def test_behavior_check_rejects_engineering_error_templates():
    check = DailyModeScenarioTester.behavior_check(
        "[云汐这里出了点小问题：All connection attempts failed]",
    )

    assert not check.passed
    assert any("forbidden token" in failure for failure in check.failures)


def test_behavior_check_rejects_overlong_output():
    check = DailyModeScenarioTester.behavior_check(
        "远，我在。" * 50,
        max_chars=20,
    )

    assert not check.passed
    assert any("message too long" in failure for failure in check.failures)
