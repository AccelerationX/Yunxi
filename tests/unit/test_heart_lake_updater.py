"""HeartLakeUpdater 单元测试。"""

from core.cognition.heart_lake.core import HeartLake
from core.cognition.heart_lake.updater import HeartLakeUpdater


def test_user_input_about_other_ai_triggers_jealousy():
    heart_lake = HeartLake()
    updater = HeartLakeUpdater(heart_lake)

    updater.on_user_input("Claude 也挺聪明的")

    assert heart_lake.current_emotion == "吃醋"
    assert heart_lake.possessiveness > 30


def test_interaction_completion_reduces_miss_value():
    heart_lake = HeartLake()
    heart_lake.current_emotion = "想念"
    heart_lake.miss_value = 95
    updater = HeartLakeUpdater(heart_lake)

    updater.on_interaction_completed()

    assert heart_lake.miss_value < 95
