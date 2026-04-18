"""HeartLake v2 感知→情感深度链路单元测试。"""

from core.cognition.heart_lake.core import HeartLake
from domains.perception.coordinator import (
    PerceptionEvent,
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
)


def _make_snapshot(
    *,
    activity_state: str = "",
    app: str = "",
    fullscreen: bool = False,
    input_rate: float = 0,
    idle: float = 0,
    hour: int = 12,
) -> PerceptionSnapshot:
    return PerceptionSnapshot(
        time_context=TimeContext(hour=hour),
        user_presence=UserPresence(
            focused_application=app,
            activity_state=activity_state,
            is_fullscreen=fullscreen,
            input_events_per_minute=input_rate,
            idle_duration=idle,
        ),
    )


# ------------------------------------------------------------------
# miss_value dynamics
# ------------------------------------------------------------------

def test_away_state_accelerates_miss():
    """away 状态：想念值加速上升。"""
    hl = HeartLake()
    hl.miss_value = 30
    snapshot = _make_snapshot(activity_state="away", idle=1200)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.miss_value > 30 + 1.5  # 60/30 = +2.0 per minute


def test_work_fullscreen_high_input_suppresses_miss():
    """work + fullscreen + 高输入：想念值下降（知道他忙）。"""
    hl = HeartLake()
    hl.miss_value = 50
    snapshot = _make_snapshot(activity_state="work", fullscreen=True, input_rate=20, idle=0)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.miss_value < 50  # 下降


def test_game_state_slightly_increases_miss():
    """game 状态：想念值微升。"""
    hl = HeartLake()
    hl.miss_value = 30
    snapshot = _make_snapshot(activity_state="game", fullscreen=True, idle=0)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert 30 < hl.miss_value < 31  # 60/90 = +0.67


# ------------------------------------------------------------------
# security dynamics
# ------------------------------------------------------------------

def test_away_state_decreases_security():
    """away 状态：安全感下降。"""
    hl = HeartLake()
    hl.security = 80
    snapshot = _make_snapshot(activity_state="away", idle=1200)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.security < 80


def test_work_fullscreen_increases_security():
    """work + fullscreen：安全感微升（知道他专注工作，安心）。"""
    hl = HeartLake()
    hl.security = 70
    snapshot = _make_snapshot(activity_state="work", fullscreen=True, input_rate=15, idle=0)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.security > 70


# ------------------------------------------------------------------
# other dimension dynamics
# ------------------------------------------------------------------

def test_late_night_work_increases_tenderness():
    """深夜 + work：温柔/心疼感上升。"""
    hl = HeartLake()
    hl.tenderness = 50
    snapshot = _make_snapshot(activity_state="work", fullscreen=True, input_rate=15, idle=0, hour=23)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.tenderness > 50


def test_game_fullscreen_increases_playfulness():
    """game + fullscreen：俏皮感上升。"""
    hl = HeartLake()
    hl.playfulness = 40
    snapshot = _make_snapshot(activity_state="game", fullscreen=True, idle=0)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.playfulness > 40


def test_away_with_low_security_increases_vulnerability():
    """away + 低安全感：脆弱感上升（需足够时长抵消自然恢复）。"""
    hl = HeartLake()
    hl.security = 40
    hl.vulnerability = 30
    snapshot = _make_snapshot(activity_state="away", idle=1200)
    hl.update_from_perception(snapshot, [], elapsed_seconds=300)  # 5 分钟
    assert hl.vulnerability > 30


# ------------------------------------------------------------------
# emotion state transitions
# ------------------------------------------------------------------

def test_away_with_high_miss_becomes_miss():
    """away + 高想念 → current_emotion = 想念。"""
    hl = HeartLake()
    hl.miss_value = 65
    snapshot = _make_snapshot(activity_state="away", idle=1200)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.current_emotion == "想念"


def test_late_night_work_with_miss_becomes_worried():
    """深夜工作 + 想念 → current_emotion = 担心（心疼）。"""
    hl = HeartLake()
    hl.miss_value = 55
    snapshot = _make_snapshot(activity_state="work", fullscreen=True, input_rate=15, idle=0, hour=23)
    hl.update_from_perception(snapshot, [], elapsed_seconds=60)
    assert hl.current_emotion == "担心"


def test_user_returned_increases_playfulness():
    """user_returned 事件：不仅开心，还增加俏皮感。"""
    hl = HeartLake()
    hl.playfulness = 40
    snapshot = _make_snapshot(activity_state="leisure", idle=0)
    events = [PerceptionEvent("user_returned", "远回到电脑前")]
    hl.update_from_perception(snapshot, events, elapsed_seconds=60)
    assert hl.current_emotion == "开心"
    assert hl.playfulness > 40
