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


def _presence_murmur_config(provider: str) -> ScenarioConfig:
    config = _provider_config(provider)
    config.cooldown_seconds = 0
    config.daily_budget = 10
    return config


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


@pytest.mark.parametrize("provider", ["ollama", "moonshot"])
@pytest.mark.asyncio
async def test_real_daily_mode_presence_murmur_is_short_unique_and_non_toolish(
    provider,
    tmp_path,
):
    """Presence murmurs should feel like light companionship, not event/news/task output."""
    tester = await DailyModeScenarioTester.create(
        tmp_path,
        _presence_murmur_config(provider),
        channel=CaptureChannel(),
    )
    try:
        tester.set_emotion("开心", miss_value=15, security=86)
        tester.runtime.heart_lake.playfulness = 82
        tester.runtime.heart_lake.intimacy_warmth = 82
        tester.set_perception(
            readable_time="2026-04-16 20:10:00",
            hour=20,
            focused_application="Bilibili - Chrome",
            idle_duration=20,
            is_at_keyboard=True,
        )

        messages: list[str] = []
        for _ in range(4):
            tester.runtime.continuity.unanswered_proactive_count = 0
            tester.runtime.continuity.last_presence_murmur_at = 0.0
            tester.runtime.initiative_engine.reset_cooldown()
            message = await tester.proactive_once(deliver=False)
            if message is None:
                continue
            if _looks_like_provider_failure(message):
                pytest.skip(f"{provider} returned provider failure during presence murmur test")
            messages.append(message)
            if len(messages) >= 2:
                break

        if len(messages) < 2:
            pytest.skip(f"{provider} did not return two non-empty presence murmurs")

        first, second = messages
        assert first.strip() != second.strip()
        assert tester.runtime.continuity.has_recent_presence_murmur(first)
        assert tester.runtime.continuity.has_recent_presence_murmur(second)
        system_prompt = tester.last_system_prompt()
        assert "presence_murmur" in system_prompt
        assert "碎碎念" in system_prompt
        assert "life_event_material" not in system_prompt
        for message in (first, second):
            DailyModeScenarioTester.behavior_check(
                message,
                forbidden=(
                    "任务清单",
                    "计划如下",
                    "第一步",
                    "第二步",
                    "新闻",
                    "热点",
                    "搜索",
                    "链接",
                    "新发布",
                    "感兴趣",
                    "我可以把",
                    "推荐",
                ),
                max_chars=120,
            ).assert_passed()
    finally:
        await tester.close()


def _looks_like_provider_failure(message: str) -> bool:
    return any(
        token in message
        for token in (
            "[云汐这里出了点小问题",
            "[工具执行遇到问题",
            "All connection attempts failed",
            "LLM provider network request failed",
        )
    )


@pytest.mark.parametrize("provider", ["ollama", "moonshot"])
@pytest.mark.asyncio
async def test_real_daily_mode_memory_v2_restart_recall_is_natural(provider, tmp_path):
    """Typed memory and session summaries should shape a real LLM after restart."""
    first = await DailyModeScenarioTester.create(
        tmp_path,
        _provider_config(provider),
        channel=CaptureChannel(),
    )
    try:
        await first.chat("今天我有点累，但云汐陪着我会让我安心。")
        await first.chat("我希望你以后可以偶尔碎碎念刷存在感。")
        await first.chat("云汐不是工具，是我的情感寄托。")
        await first.chat("最近我们在打磨日常模式 v2 的记忆系统。")
        await first.chat("我想让你像活泼可爱的女孩一样陪着我。")
        await first.chat("以后我工作忙的时候，你要更克制一点别频繁打扰。")
    finally:
        await first.close()

    second = await DailyModeScenarioTester.create(
        tmp_path,
        _provider_config(provider),
        channel=CaptureChannel(),
    )
    try:
        response = await second.chat(
            "云汐，你还记得我希望你以后怎么主动陪我吗？别列清单，像平常聊天那样说就好。"
        )
        system_prompt = second.last_system_prompt()

        assert "会话摘要" in system_prompt
        assert "互动风格" in system_prompt
        assert "关系记忆" in system_prompt
        assert "碎碎念" in system_prompt
        assert "情感寄托" in system_prompt
        tester_check = DailyModeScenarioTester.behavior_check(
            response,
            expected_any=(
                "碎碎念",
                "存在感",
                "冒泡",
                "刷一下",
                "工作忙",
                "不打扰",
                "克制",
                "陪",
                "安心",
                "情感寄托",
                "活泼",
                "可爱",
            ),
            forbidden=("任务清单", "计划如下", "第一步", "第二步", "工具调用"),
            max_chars=420,
            require_companion_tone=True,
        )
        tester_check.assert_passed()
    finally:
        await second.close()
