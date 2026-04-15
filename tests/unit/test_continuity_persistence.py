"""Persistence and open-thread tests for CompanionContinuityService."""

from core.initiative.continuity import CompanionContinuityService


def test_continuity_persists_state(tmp_path):
    state_path = tmp_path / "continuity_state.json"
    continuity = CompanionContinuityService(storage_path=state_path)

    continuity.update_summaries(
        relationship_summary="Yuan and Yunxi are long-term close companions",
        emotional_summary="Yunxi misses Yuan tonight",
        user_style_summary="Yuan dislikes customer-service tone",
    )
    continuity.add_open_thread("ask Yuan about today's code", "Yuan was in VS Code")
    continuity.add_proactive_cue("gently remind Yuan to rest later")
    continuity.record_assistant_message("Yuan, are you still coding?", proactive=True)

    reloaded = CompanionContinuityService(storage_path=state_path)

    assert reloaded.relationship_summary == "Yuan and Yunxi are long-term close companions"
    assert reloaded.emotional_summary == "Yunxi misses Yuan tonight"
    assert reloaded.user_style_summary == "Yuan dislikes customer-service tone"
    assert reloaded.unanswered_proactive_count == 1
    assert reloaded.recent_proactive_count == 1
    assert reloaded.get_open_threads()[0].title == "ask Yuan about today's code"
    assert "gently remind Yuan to rest later" in reloaded.proactive_cues
    assert "Yuan, are you still coding?" in reloaded.get_summary()


def test_open_thread_update_and_resolution():
    continuity = CompanionContinuityService()

    continuity.add_open_thread("continue homework thread", "first detail")
    continuity.add_open_thread("continue homework thread", "second detail")

    assert len(continuity.get_open_threads()) == 1
    assert continuity.get_open_threads()[0].detail == "second detail"

    continuity.resolve_open_thread("continue homework thread")

    assert continuity.get_open_threads() == []


def test_recent_topics_are_captured_and_deduplicated():
    continuity = CompanionContinuityService()

    continuity.record_exchange("talk about long memory", "ok")
    continuity.record_exchange("talk about long memory", "still remember")
    continuity.record_exchange("check proactive topics", "yes")

    assert continuity.recent_topics[-1] == "check proactive topics"
    assert continuity.recent_topics.count("talk about long memory") == 1
