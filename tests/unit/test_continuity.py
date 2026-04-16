"""CompanionContinuityService 单元测试。"""

from core.initiative.continuity import CompanionContinuityService


def test_continuity_records_and_summarizes_exchanges():
    continuity = CompanionContinuityService(max_exchanges=3)

    continuity.record_exchange("你好", "远～我在")
    continuity.record_assistant_message("远，你还在忙吗？", proactive=True)

    summary = continuity.get_summary()
    assert "远：你好" in summary
    assert "云汐：远～我在" in summary
    assert "云汐（主动）：远，你还在忙吗？" in summary
    assert continuity.unanswered_proactive_count == 1


def test_continuity_trims_to_max_exchanges():
    continuity = CompanionContinuityService(max_exchanges=2)

    continuity.record_exchange("1", "a")
    continuity.record_exchange("2", "b")
    continuity.record_exchange("3", "c")

    assert len(continuity.exchanges) == 2
    assert continuity.exchanges[0].user_message == "2"


def test_user_reply_resets_unanswered_proactive_count():
    continuity = CompanionContinuityService()

    continuity.record_assistant_message("远～", proactive=True)
    continuity.record_exchange("我在", "好呀")

    assert continuity.unanswered_proactive_count == 0


def test_presence_murmurs_reach_summary_as_do_not_repeat_context():
    continuity = CompanionContinuityService()

    continuity.record_presence_murmur("云汐路过一下")

    summary = continuity.get_summary()

    assert "recent_presence_murmurs_do_not_repeat_exactly" in summary
    assert "云汐路过一下" in summary
