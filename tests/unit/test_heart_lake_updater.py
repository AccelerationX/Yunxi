"""HeartLakeUpdater 单元测试。"""

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import HeartLakeUpdater


def test_user_input_about_other_ai_triggers_jealousy():
    heart_lake = HeartLake()
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input("Claude 也挺聪明的")

    assert heart_lake.current_emotion == "吃醋"
    assert heart_lake.possessiveness > 30
    assert "轻微吃醋" in heart_lake.compound_labels


def test_tired_user_input_triggers_tender_concern():
    heart_lake = HeartLake()
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input("我今天真的有点累，不想做任务，只想你陪我一下")

    assert heart_lake.current_emotion == "担心"
    assert heart_lake.tenderness > 55
    assert heart_lake.attachment > 55
    assert "担心但想陪着" in heart_lake.compound_labels


def test_relationship_memory_strengthens_warmth_appraisal():
    heart_lake = HeartLake()
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input(
        "你陪着我会让我安心",
        memory_summary="关系记忆：云汐不是工具，是远的情感寄托",
    )

    assert heart_lake.current_emotion == "开心"
    assert heart_lake.security > 80
    assert heart_lake.intimacy_warmth > 60
    assert "关系被记起" in heart_lake.compound_labels


def test_boundary_feedback_makes_yunxi_more_restrained():
    heart_lake = HeartLake()
    heart_lake.playfulness = 60
    heart_lake.miss_value = 60
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input("我工作忙的时候你别频繁打扰，会有点烦")

    assert heart_lake.current_emotion == "委屈"
    assert heart_lake.vulnerability > 20
    assert heart_lake.playfulness < 60
    assert heart_lake.miss_value < 60
    assert "被提醒边界" in heart_lake.compound_labels


def test_repeated_same_appraisal_is_softened_by_cooldown():
    heart_lake = HeartLake()
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input("Claude 也挺聪明的")
    first_possessiveness = heart_lake.possessiveness
    updater.on_user_input("Claude 真的也挺聪明的")
    second_delta = heart_lake.possessiveness - first_possessiveness

    assert first_possessiveness > 30
    assert 0 < second_delta < 8


def test_natural_recovery_moves_volatile_dimensions_toward_baseline():
    heart_lake = HeartLake()
    heart_lake.current_emotion = "委屈"
    heart_lake.vulnerability = 70
    heart_lake.playfulness = 20
    heart_lake.valence = -40

    heart_lake.apply_natural_recovery(elapsed_seconds=720)

    assert heart_lake.vulnerability < 70
    assert heart_lake.playfulness > 20
    assert heart_lake.valence > -40


def test_recovery_can_clear_resolved_negative_emotion():
    heart_lake = HeartLake()
    heart_lake.current_emotion = "委屈"
    heart_lake.vulnerability = 21
    heart_lake.compound_labels = ["被提醒边界"]

    heart_lake.apply_natural_recovery(elapsed_seconds=720)

    assert heart_lake.current_emotion == "平静"
    assert heart_lake.compound_labels == []


def test_interaction_completion_reduces_miss_value():
    heart_lake = HeartLake()
    heart_lake.current_emotion = "想念"
    heart_lake.miss_value = 95
    updater = HeartLakeUpdater(heart_lake)

    updater.on_interaction_completed()

    assert heart_lake.miss_value < 95
