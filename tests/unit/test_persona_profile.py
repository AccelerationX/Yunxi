"""Tests for structured persona and relationship profiles."""

from core.persona.profile import load_persona_profile
from core.prompt_builder import RuntimeContext, YunxiPromptBuilder
from domains.memory.relationship_profile import load_user_relationship_profile


def test_load_default_yunxi_persona_profile():
    profile = load_persona_profile()

    assert profile.name == "\u4e91\u6c50"
    assert "\u4f4f\u5728\u8fdc\u7535\u8111\u91cc" in profile.identity
    assert "\u673a\u68b0\u5ba2\u670d\u8154" in profile.forbidden_tones


def test_load_default_relationship_profile():
    profile = load_user_relationship_profile()

    assert profile.preferred_name == "\u8fdc"
    assert any("\u9999\u6e2f\u4e2d\u6587\u5927\u5b66" in fact for fact in profile.facts)
    assert "\u7f16\u7a0b" in profile.interests
    assert "\u8fc7\u5ea6\u8089\u9ebb" in profile.dislikes


def test_prompt_builder_injects_persona_and_relationship_profiles():
    builder = YunxiPromptBuilder()
    prompt = builder.build_system_prompt(RuntimeContext())

    assert "\u4e91\u6c50" in prompt
    assert "\u4f4f\u5728\u8fdc\u7535\u8111\u91cc" in prompt
    assert "\u9999\u6e2f\u4e2d\u6587\u5927\u5b66\uff08\u6df1\u5733\uff09" in prompt
    assert "\u673a\u68b0\u5ba2\u670d\u8154" in prompt
    assert "\u9ad8\u7ea7\u811a\u672c\u6267\u884c\u7a0b\u5e8f" in prompt
