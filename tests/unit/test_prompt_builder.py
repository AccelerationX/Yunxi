"""PromptBuilder 单元测试。"""

from domains.perception.coordinator import (
    PerceptionSnapshot,
    TimeContext,
    UserPresence,
    SystemState,
    ExternalInfo,
)
from core.cognition.heart_lake.core import HeartLake
from core.prompt_builder import PromptConfig, RuntimeContext, YunxiPromptBuilder


def test_identity_section_always_present():
    builder = YunxiPromptBuilder(PromptConfig(enable_identity=True))
    ctx = RuntimeContext()
    prompt = builder.build_system_prompt(ctx)
    assert "云汐" in prompt


def test_failure_hints_in_prompt():
    builder = YunxiPromptBuilder(PromptConfig(enable_failure_hints=True))
    ctx = RuntimeContext(failure_hints="截图工具在暗色模式下容易失效，注意对比度。")
    prompt = builder.build_system_prompt(ctx)
    assert "历史经验提醒" in prompt
    assert "暗色模式" in prompt


def test_failure_hints_disabled():
    builder = YunxiPromptBuilder(PromptConfig(enable_failure_hints=False))
    ctx = RuntimeContext(failure_hints="截图工具在暗色模式下容易失效。")
    prompt = builder.build_system_prompt(ctx)
    assert "历史经验提醒" not in prompt


def test_continuity_summary_in_prompt():
    builder = YunxiPromptBuilder(PromptConfig(enable_continuity=True))
    ctx = RuntimeContext(
        continuity_summary=(
            "open_threads:\n"
            "- ask Yuan about today's code - Yuan was in VS Code\n"
            "recent_topics: long memory"
        )
    )
    prompt = builder.build_system_prompt(ctx)
    assert "open_threads" in prompt
    assert "ask Yuan about today's code" in prompt
    assert "long memory" in prompt


def test_available_tools_in_prompt():
    builder = YunxiPromptBuilder(PromptConfig(enable_tools=True))
    ctx = RuntimeContext(available_tools=["clipboard_read", "screenshot_capture"])
    prompt = builder.build_system_prompt(ctx)
    assert "clipboard_read" in prompt
    assert "screenshot_capture" in prompt


def test_perception_focused_application():
    builder = YunxiPromptBuilder(PromptConfig(enable_perception=True))
    snapshot = PerceptionSnapshot(
        time_context=TimeContext(readable_time="2026-04-15 10:00"),
        user_presence=UserPresence(
            focused_application="VS Code",
            foreground_process_name="Code.exe",
            idle_duration=0,
            input_events_per_minute=18,
        ),
        system_state=SystemState(cpu_percent=45),
        external_info=ExternalInfo(weather="晴朗 22°C"),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)
    assert "VS Code" in prompt
    assert "Code.exe" in prompt
    assert "work" in prompt
    assert "18次/分钟" in prompt
    assert "45%" in prompt
    assert "晴朗" in prompt


def test_perception_includes_fullscreen_state():
    builder = YunxiPromptBuilder(PromptConfig(enable_perception=True))
    snapshot = PerceptionSnapshot(
        user_presence=UserPresence(
            focused_application="Steam Game",
            foreground_process_name="game.exe",
            is_fullscreen=True,
        ),
    )

    prompt = builder.build_system_prompt(RuntimeContext(perception_snapshot=snapshot))

    assert "全屏" in prompt
    assert "game.exe" in prompt
    assert "game" in prompt


def test_emotion_section_content():
    builder = YunxiPromptBuilder(PromptConfig(enable_emotion=True))
    hl = HeartLake()
    hl.current_emotion = "想念"
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)
    assert "想念" in prompt
    assert "表达思念" in prompt


def test_emotion_section_includes_compound_labels():
    builder = YunxiPromptBuilder(PromptConfig(enable_emotion=True))
    hl = HeartLake()
    hl.current_emotion = "担心"
    hl.compound_labels = ["担心但想陪着", "关系被记起"]
    ctx = RuntimeContext(heart_lake_state=hl)

    prompt = builder.build_system_prompt(ctx)

    assert "复合情绪线索" in prompt
    assert "担心但想陪着" in prompt
    assert "关系被记起" in prompt


def test_reaction_guidance_uses_user_input_without_template_copy():
    builder = YunxiPromptBuilder(PromptConfig(enable_reaction_guidance=True))
    hl = HeartLake()
    hl.current_emotion = "担心"
    ctx = RuntimeContext(
        heart_lake_state=hl,
        user_input="我今天有点累，只想你陪我一下",
    )

    prompt = builder.build_system_prompt(ctx)

    assert "当前反应参考" in prompt
    assert "安慰与陪伴" in prompt
    assert "不要照抄示例" in prompt
    assert "不要输出反应库字段名" in prompt


def test_factory_mode_section():
    builder = YunxiPromptBuilder(PromptConfig(enable_mode=True))
    ctx = RuntimeContext(mode="factory", factory_status="正在构建 yunxi-pet")
    prompt = builder.build_system_prompt(ctx)
    assert "工厂模式" in prompt
    assert "yunxi-pet" in prompt


def test_presence_murmur_proactive_prompt_uses_strict_low_content_boundary():
    builder = YunxiPromptBuilder(PromptConfig())
    ctx = RuntimeContext(
        initiative_context=(
            "initiative_decision:\n"
            "- intent: presence_murmur\n"
            "- expression_mode: presence_murmur\n"
        )
    )

    prompt = builder.build_proactive_prompt(ctx)

    assert "轻轻刷一下存在感" in prompt
    assert "不要开启话题" in prompt
    assert "不要分享新闻、热点、链接、资料或新发布内容" in prompt
    assert "不要说“我发现了什么”“要不要我发给你”“你感兴趣的话”" in prompt
    assert "现在你想主动找他聊点什么" not in prompt
