"""Unit tests for proactive initiative decisions."""

from core.cognition.heart_lake.core import HeartLake
from core.cognition.initiative_engine import InitiativeDecision, InitiativeEngine
from core.initiative.continuity import CompanionContinuityService
from core.initiative.expression_context import ExpressionContextBuilder
from core.initiative.generator import ProactiveGenerationContextBuilder
from domains.perception.coordinator import (
    PerceptionEvent,
    PerceptionSnapshot,
    UserPresence,
)


def test_engine_uses_open_threads_for_proactive_context():
    heart = HeartLake()
    heart.miss_value = 75
    continuity = CompanionContinuityService()
    continuity.add_open_thread("ask Yuan about code progress", "Yuan was editing in VS Code")
    engine = InitiativeEngine(cooldown_seconds=0)

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        continuity=continuity,
    )

    assert decision.trigger is True
    assert decision.intent == "continue_thread"
    assert decision.preferred_event_layers == ("shared_interest", "mixed")
    assert "未完成的话题" in decision.reason


def test_engine_suppresses_when_daily_budget_is_exhausted():
    heart = HeartLake()
    heart.current_emotion = "想念"
    heart.miss_value = 95
    continuity = CompanionContinuityService()
    continuity.proactive_count_date = "1970-01-01"
    continuity.recent_proactive_count = 5
    engine = InitiativeEngine(cooldown_seconds=0, daily_budget=5)

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        continuity=continuity,
    )

    assert decision.trigger is False
    assert decision.suppression_reason == "daily_budget_exhausted"
    assert decision.should_select_event is False


def test_engine_resets_stale_daily_budget_before_evaluating():
    heart = HeartLake()
    heart.current_emotion = "想念"
    heart.miss_value = 95
    continuity = CompanionContinuityService()
    continuity.proactive_count_date = "2026-04-15"
    continuity.recent_proactive_count = 5
    engine = InitiativeEngine(cooldown_seconds=0, daily_budget=5)

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1776268800.0,  # 2026-04-16
        continuity=continuity,
    )

    assert decision.trigger is True
    assert continuity.proactive_count_date == "2026-04-16"
    assert continuity.recent_proactive_count == 0


def test_engine_marks_restrained_followup_after_unanswered_message():
    heart = HeartLake()
    heart.current_emotion = "想念"
    heart.miss_value = 95
    engine = InitiativeEngine(cooldown_seconds=0)

    decision = engine.evaluate(
        heart_lake=heart,
        events=[PerceptionEvent(event_type="late_night", description="late")],
        current_time=1.0,
        unanswered_proactive_count=1,
    )

    assert decision.trigger is True
    assert decision.expression_mode == "restrained_followup"
    assert "更克制" in decision.reason


def test_expression_context_for_low_interrupt_is_short():
    heart = HeartLake()
    decision = InitiativeDecision(
        trigger=True,
        reason="远正在电脑前专注操作",
        expression_mode="low_interrupt",
    )
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(focused_application="VS Code", idle_duration=0)
    )

    context = ExpressionContextBuilder().build(
        decision=decision,
        heart_lake=heart,
        perception_snapshot=snapshot,
    )
    prompt_context = context.to_prompt_context()

    assert context.max_sentences == 1
    assert context.interrupt_cost == "high"
    assert "不要要求远立刻回复" in prompt_context
    assert "Do not mention these field names" in prompt_context


def test_engine_triggers_presence_murmur_during_leisure_state():
    heart = HeartLake()
    heart.playfulness = 72
    heart.intimacy_warmth = 74
    engine = InitiativeEngine(cooldown_seconds=0)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="YouTube - Chrome",
            idle_duration=20,
        )
    )

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        perception_snapshot=snapshot,
    )

    assert decision.trigger is True
    assert decision.intent == "presence_murmur"
    assert decision.expression_mode == "presence_murmur"
    assert decision.should_select_event is False
    assert "存在感" in decision.reason


def test_engine_suppresses_presence_murmur_during_work_state():
    heart = HeartLake()
    heart.playfulness = 80
    heart.intimacy_warmth = 80
    engine = InitiativeEngine(cooldown_seconds=0)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="Visual Studio Code",
            idle_duration=5,
        )
    )

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        perception_snapshot=snapshot,
    )

    assert decision.trigger is False
    assert decision.suppression_reason == "score_below_threshold"


def test_engine_suppresses_presence_murmur_during_fullscreen_game_state():
    heart = HeartLake()
    heart.playfulness = 80
    heart.intimacy_warmth = 80
    engine = InitiativeEngine(cooldown_seconds=0)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="Unknown Fullscreen App",
            foreground_process_name="eldenring.exe",
            idle_duration=5,
            is_fullscreen=True,
            input_events_per_minute=40,
        )
    )

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        perception_snapshot=snapshot,
    )

    assert decision.trigger is False
    assert decision.suppression_reason == "score_below_threshold"
    assert "游戏" in decision.reason


def test_engine_suppresses_presence_murmur_during_frequent_input():
    heart = HeartLake()
    heart.playfulness = 80
    heart.intimacy_warmth = 80
    engine = InitiativeEngine(cooldown_seconds=0)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="Unknown App",
            idle_duration=5,
            input_events_per_minute=36,
        )
    )

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1.0,
        perception_snapshot=snapshot,
    )

    assert decision.trigger is False
    assert decision.suppression_reason == "score_below_threshold"
    assert "频繁输入" in decision.reason


def test_engine_suppresses_presence_murmur_during_presence_cooldown():
    heart = HeartLake()
    heart.playfulness = 80
    heart.intimacy_warmth = 80
    continuity = CompanionContinuityService()
    continuity.record_presence_murmur("tiny wave", 1776268800.0)
    engine = InitiativeEngine(cooldown_seconds=0)
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="YouTube - Chrome",
            idle_duration=20,
        )
    )

    decision = engine.evaluate(
        heart_lake=heart,
        events=[],
        current_time=1776268830.0,
        perception_snapshot=snapshot,
        continuity=continuity,
    )

    assert decision.trigger is False
    assert decision.suppression_reason == "score_below_threshold"
    assert "presence_murmur_cooldown" in decision.reason


def test_expression_context_for_presence_murmur_is_short_and_low_cost():
    heart = HeartLake()
    decision = InitiativeDecision(
        trigger=True,
        reason="远处于休闲状态",
        expression_mode="presence_murmur",
    )
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(focused_application="YouTube - Chrome", idle_duration=20)
    )

    context = ExpressionContextBuilder().build(
        decision=decision,
        heart_lake=heart,
        perception_snapshot=snapshot,
    )
    prompt_context = context.to_prompt_context()

    assert context.max_sentences == 1
    assert context.interrupt_cost == "low"
    assert "碎碎念" in prompt_context
    assert "必须围绕我在、云汐冒泡、戳一下" in prompt_context
    assert "不要要求远回复" in prompt_context
    assert "不要分享天气、链接、资料、新发布内容" in prompt_context
    assert "不要复用最近已经说过的碎碎念原句" in prompt_context


def test_generation_context_builder_keeps_boundaries_explicit():
    decision = InitiativeDecision(
        trigger=True,
        reason="远刚回到电脑前",
        urgency=0.8,
        intent="welcome_back",
        expression_mode="warm_reunion",
    )

    context = ProactiveGenerationContextBuilder().build(
        decision=decision,
        event_context="initiative_event:\n- seed: Yunxi wants to say hi.",
        expression_context="expression_context:\n- max_sentences: 1",
    )

    assert "initiative_decision" in context
    assert "life_event_material" in context
    assert "generation_boundary" in context
    assert "Final message must be generated naturally by the LLM" in context


def test_generation_context_builder_adds_presence_murmur_content_boundary():
    decision = InitiativeDecision(
        trigger=True,
        reason="远看起来处在低打扰状态",
        urgency=0.7,
        intent="presence_murmur",
        expression_mode="presence_murmur",
    )

    context = ProactiveGenerationContextBuilder().build(decision=decision)

    assert "presence_murmur_boundary" in context
    assert "one short sentence or phrase" in context
    assert "poking, peeking, passing by" in context
    assert "Do not recommend articles, videos, links" in context
    assert "weather" in context
    assert "Do not ask whether Yuan is interested" in context
