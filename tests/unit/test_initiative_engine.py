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
