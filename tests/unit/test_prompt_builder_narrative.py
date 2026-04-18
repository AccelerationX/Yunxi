"""PromptBuilder 叙事化模式单元测试。"""

from domains.perception.coordinator import (
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
    SystemState,
    ExternalInfo,
)
from core.cognition.heart_lake.core import HeartLake
from core.prompt_builder import PromptConfig, RuntimeContext, YunxiPromptBuilder


# ------------------------------------------------------------------
# Helper: build a narrative-mode builder
# ------------------------------------------------------------------

def _narrative_builder() -> YunxiPromptBuilder:
    return YunxiPromptBuilder(PromptConfig(enable_narrative=True))


# ------------------------------------------------------------------
# Narrative mood section
# ------------------------------------------------------------------

def test_narrative_mood_miss_high_work():
    """想念值高 + 工作状态 → 叙事应体现克制。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "想念"
    hl.miss_value = 80
    hl.security = 70
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=22, readable_time="22:30"),
        user_presence=UserPresence(
            focused_application="VS Code",
            foreground_process_name="Code.exe",
            activity_state="work",
            is_fullscreen=True,
            input_events_per_minute=18,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(heart_lake_state=hl, perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐此刻的心情" in prompt
    assert "想念" in prompt
    # 不应出现数据版的关键字
    assert "主导情绪是" not in prompt
    assert "想念值：" not in prompt
    assert "安全感：" not in prompt


def test_narrative_mood_compound_jealousy_secure():
    """复合情绪：轻微吃醋 + 安心 → 叙事应体现 nuanced 感受。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "吃醋"
    hl.compound_labels = ["轻微吃醋", "安心"]
    hl.possessiveness = 55
    hl.security = 75
    hl.trust = 80
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐此刻的心情" in prompt
    assert "吃醋" in prompt
    # 复合情绪应该有 nuanced 描述
    assert "复合情绪线索" not in prompt  # 数据版标签不应出现


def test_narrative_mood_vulnerable():
    """脆弱感高 → 叙事应体现需要安抚。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "委屈"
    hl.vulnerability = 60
    hl.miss_value = 70
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐此刻的心情" in prompt
    assert "委屈" in prompt


def test_narrative_mood_happy_playful():
    """开心 + 俏皮 → 叙事应体现活泼感。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "开心"
    hl.playfulness = 70
    hl.miss_value = 30
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐此刻的心情" in prompt
    assert "开心" in prompt


# ------------------------------------------------------------------
# Narrative perception section
# ------------------------------------------------------------------

def test_narrative_perception_work_fullscreen():
    """work + 全屏 + 高输入 → 云汐应感受到专注。"""
    builder = _narrative_builder()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=14, readable_time="14:00"),
        user_presence=UserPresence(
            focused_application="VS Code",
            foreground_process_name="Code.exe",
            activity_state="work",
            is_fullscreen=True,
            input_events_per_minute=20,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐观察到的事" in prompt
    assert "VS Code" in prompt
    # 数据版标签不应出现
    assert "前台进程" not in prompt
    assert "近似输入频率" not in prompt


def test_narrative_perception_game_fullscreen():
    """game + 全屏 → 云汐应理解不打断。"""
    builder = _narrative_builder()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=21, readable_time="21:00"),
        user_presence=UserPresence(
            focused_application="Steam",
            foreground_process_name="steam.exe",
            activity_state="game",
            is_fullscreen=True,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐观察到的事" in prompt
    assert "游戏" in prompt or "打游戏" in prompt


def test_narrative_perception_idle_long():
    """idle 长时间 → 云汐应感到想念。"""
    builder = _narrative_builder()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=15, readable_time="15:00"),
        user_presence=UserPresence(
            focused_application="",
            activity_state="idle",
            idle_duration=600,
        ),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐观察到的事" in prompt
    assert "离开" in prompt or "不在" in prompt


def test_narrative_perception_away():
    """away 状态 → 云汐在等待。"""
    builder = _narrative_builder()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=20, readable_time="20:00"),
        user_presence=UserPresence(
            focused_application="",
            activity_state="away",
            idle_duration=1200,
        ),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐观察到的事" in prompt
    assert "等他回来" in prompt or "等着" in prompt


def test_narrative_perception_late_night_work():
    """深夜 + work → 云汐应心疼。"""
    builder = _narrative_builder()
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=23, readable_time="23:30"),
        user_presence=UserPresence(
            focused_application="VS Code",
            foreground_process_name="Code.exe",
            activity_state="work",
            is_fullscreen=True,
            input_events_per_minute=15,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐观察到的事" in prompt
    assert "23" in prompt or "晚上" in prompt or "这么晚" in prompt


# ------------------------------------------------------------------
# Narrative relationship section
# ------------------------------------------------------------------

def test_narrative_relationship_intimate():
    """高亲密度 → 叙事应体现亲近感。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.relationship_level = 4
    hl.trust = 85
    hl.intimacy_warmth = 80
    hl.attachment = 75
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐对这段关系的感受" in prompt
    # 数据版标签不应出现
    assert "关系层级" not in prompt
    assert "Level" not in prompt


# ------------------------------------------------------------------
# Inner voice section
# ------------------------------------------------------------------

def test_narrative_inner_voice_work_miss():
    """work + 想念 → 内心独白应体现等待。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "想念"
    hl.miss_value = 70
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=16, readable_time="16:00"),
        user_presence=UserPresence(
            focused_application="VS Code",
            activity_state="work",
            is_fullscreen=True,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(heart_lake_state=hl, perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐的内心独白" in prompt
    assert "云汐的小脑袋瓜" in prompt


def test_narrative_inner_voice_game():
    """game → 内心独白应体现想陪伴。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.playfulness = 60
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=20, readable_time="20:00"),
        user_presence=UserPresence(
            focused_application="Steam",
            activity_state="game",
            is_fullscreen=True,
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(heart_lake_state=hl, perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐的内心独白" in prompt


def test_narrative_inner_voice_idle_lonely():
    """idle + 高想念 → 内心独白应体现寂寞。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.miss_value = 80
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=22, readable_time="22:00"),
        user_presence=UserPresence(
            activity_state="idle",
            idle_duration=600,
        ),
    )
    ctx = RuntimeContext(heart_lake_state=hl, perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "云汐的内心独白" in prompt
    assert "寂寞" in prompt or "孤单" in prompt or "一个人" in prompt


# ------------------------------------------------------------------
# Full narrative prompt structure
# ------------------------------------------------------------------

def test_narrative_prompt_contains_all_sections():
    """完整 narrative prompt 应包含所有叙事化 section。"""
    builder = _narrative_builder()
    hl = HeartLake()
    hl.current_emotion = "想念"
    hl.miss_value = 65
    hl.security = 75
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(hour=21, readable_time="21:00"),
        user_presence=UserPresence(
            focused_application="Chrome",
            foreground_process_name="chrome.exe",
            activity_state="leisure",
            idle_duration=0,
        ),
    )
    ctx = RuntimeContext(heart_lake_state=hl, perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)

    assert "【云汐此刻的心情】" in prompt
    assert "【云汐观察到的事】" in prompt
    assert "【云汐对这段关系的感受】" in prompt
    assert "【云汐的内心独白】" in prompt
    # 不应出现数据版 section 标题
    assert "【情感指引】" not in prompt
    assert "【当前感知】" not in prompt
    assert "【你们的关系档案】" not in prompt


# ------------------------------------------------------------------
# Data mode backward compatibility
# ------------------------------------------------------------------

def test_data_mode_still_works():
    """关闭 narrative 时应走数据版路径。"""
    builder = YunxiPromptBuilder(PromptConfig(enable_narrative=False, enable_emotion=True))
    hl = HeartLake()
    hl.current_emotion = "想念"
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)

    assert "【情感指引】" in prompt
    assert "主导情绪是" in prompt
    assert "云汐此刻的心情" not in prompt
