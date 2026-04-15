"""Phase 3: 记忆子系统（ExperienceBuffer / SkillLibrary / ParamFiller / SkillDistiller）单元测试。"""

import json
import os
import tempfile

import pytest

from domains.memory.skills.experience_buffer import ExperienceBuffer
from domains.memory.skills.param_filler import ParamFiller
from domains.memory.skills.skill_distiller import SkillDistiller
from domains.memory.skills.skill_library import SkillLibrary


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield tmpdir


class TestExperienceBuffer:
    def test_add_and_get_recent(self, temp_db_path):
        buf = ExperienceBuffer(db_path=os.path.join(temp_db_path, "exp.db"))
        buf.add(
            intent_text="查询北京天气",
            actions=[{"tool": "weather_query", "args": {"city": "北京"}}],
            outcome="success",
            source="mcp_audit",
        )
        buf.add(
            intent_text="查询上海天气",
            actions=[{"tool": "weather_query", "args": {"city": "上海"}}],
            outcome="success",
            source="mcp_audit",
        )
        recent = buf.get_recent(limit=10, source="mcp_audit")
        assert len(recent) == 2
        assert recent[0]["intent_text"] == "查询上海天气"
        assert recent[1]["intent_text"] == "查询北京天气"

    def test_get_recent_filters_by_source(self, temp_db_path):
        buf = ExperienceBuffer(db_path=os.path.join(temp_db_path, "exp.db"))
        buf.add(intent_text="a", actions=[], outcome="success", source="chat")
        buf.add(intent_text="b", actions=[], outcome="success", source="mcp_audit")
        recent = buf.get_recent(limit=10, source="mcp_audit")
        assert len(recent) == 1
        assert recent[0]["intent_text"] == "b"


class TestSkillLibrary:
    @pytest.mark.asyncio
    async def test_add_and_retrieve(self, temp_db_path):
        lib = SkillLibrary(db_path=os.path.join(temp_db_path, "skills.db"))
        await lib.initialize()

        skill = {
            "skill_name": "query_weather",
            "trigger_patterns": ["查询北京天气", "查询{city}天气"],
            "parameters": ["city"],
            "actions": [{"tool": "weather_query", "args": {"city": "{city}"}}],
        }
        lib.add_skill(skill)

        results = await lib.retrieve("查询上海天气", top_k=1, threshold=0.60)
        assert len(results) == 1
        assert results[0]["skill_name"] == "query_weather"
        assert "city" in results[0]["parameters"]

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_when_no_match(self, temp_db_path):
        lib = SkillLibrary(db_path=os.path.join(temp_db_path, "skills.db"))
        await lib.initialize()
        results = await lib.retrieve("完全不相关的内容", top_k=1, threshold=0.99)
        assert results == []

    @pytest.mark.asyncio
    async def test_record_outcome_updates_counts(self, temp_db_path):
        lib = SkillLibrary(db_path=os.path.join(temp_db_path, "skills.db"))
        await lib.initialize()
        skill = {
            "skill_name": "test_skill",
            "trigger_patterns": ["test"],
            "parameters": [],
            "actions": [],
        }
        lib.add_skill(skill)

        lib.record_outcome("test_skill", success=True)
        lib.record_outcome("test_skill", success=True)
        lib.record_outcome("test_skill", success=False)

        results = await lib.retrieve("test", top_k=1, threshold=0.0)
        assert len(results) == 1
        # success=2, fail=1 => success_rate = 2 / (2+1+1e-6)
        assert results[0]["success_rate"] == pytest.approx(2 / 3, rel=1e-3)


class TestParamFiller:
    def test_fill_city(self):
        filler = ParamFiller()
        skill = {"parameters": ["city"]}
        assert filler.fill("查询北京天气", skill) == {"city": "北京"}

    def test_fill_expression(self):
        filler = ParamFiller()
        skill = {"parameters": ["expression"]}
        assert filler.fill("计算 3+5*2", skill) == {"expression": "3+5*2"}

    def test_fill_app_name(self):
        filler = ParamFiller()
        skill = {"parameters": ["app_name"]}
        assert filler.fill("打开网易云音乐并播放", skill) == {"app_name": "网易云音乐"}

    def test_fill_multiple_params(self):
        filler = ParamFiller()
        skill = {"parameters": ["city", "expression"]}
        # 只能匹配到 city，expression 不匹配
        assert filler.fill("查询北京天气", skill) == {"city": "北京", "expression": ""}


class TestSkillDistiller:
    def test_distill_weather_skill(self):
        distiller = SkillDistiller()
        pattern = {
            "representative_intent": "查询北京天气",
            "actions": [{"tool": "weather_query", "args": {"city": "北京"}}],
            "confidence": 0.85,
        }
        skill = distiller.distill(pattern)
        assert skill["skill_name"] == "query_weather"
        assert "city" in skill["parameters"]
        assert "{city}" in skill["trigger_patterns"][1]

    def test_distill_calculate_skill(self):
        distiller = SkillDistiller()
        pattern = {
            "representative_intent": "计算 3+5",
            "actions": [{"tool": "calculator", "args": {"expression": "3+5"}}],
            "confidence": 0.9,
        }
        skill = distiller.distill(pattern)
        assert skill["skill_name"] == "calculate_expression"
        assert "expression" in skill["parameters"]
