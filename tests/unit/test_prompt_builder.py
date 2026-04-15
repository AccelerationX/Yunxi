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
        user_presence=UserPresence(focused_application="VS Code", idle_duration=0),
        system_state=SystemState(cpu_percent=45),
        external_info=ExternalInfo(weather="晴朗 22°C"),
    )
    ctx = RuntimeContext(perception_snapshot=snapshot)
    prompt = builder.build_system_prompt(ctx)
    assert "VS Code" in prompt
    assert "45%" in prompt
    assert "晴朗" in prompt


def test_emotion_section_content():
    builder = YunxiPromptBuilder(PromptConfig(enable_emotion=True))
    hl = HeartLake()
    hl.current_emotion = "想念"
    ctx = RuntimeContext(heart_lake_state=hl)
    prompt = builder.build_system_prompt(ctx)
    assert "想念" in prompt
    assert "表达思念" in prompt


def test_factory_mode_section():
    builder = YunxiPromptBuilder(PromptConfig(enable_mode=True))
    ctx = RuntimeContext(mode="factory", factory_status="正在构建 yunxi-pet")
    prompt = builder.build_system_prompt(ctx)
    assert "工厂模式" in prompt
    assert "yunxi-pet" in prompt
