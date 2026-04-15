"""Phase 3: 技能学习与记忆管理器集成测试。"""

import os
import tempfile

import pytest

from domains.memory.manager import MemoryManager
from domains.memory.skills.pattern_miner import PatternMiner


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield tmpdir


class TestPatternMiner:
    @pytest.mark.asyncio
    async def test_mine_finds_weather_pattern(self, temp_db_path):
        miner = PatternMiner()
        await miner.initialize()

        experiences = [
            {"intent_text": "查询北京天气", "actions": [{"tool": "weather", "args": {}}], "outcome": "success"},
            {"intent_text": "查询上海天气", "actions": [{"tool": "weather", "args": {}}], "outcome": "success"},
            {"intent_text": "查询广州天气", "actions": [{"tool": "weather", "args": {}}], "outcome": "success"},
            {"intent_text": "计算 1+1", "actions": [{"tool": "calc", "args": {}}], "outcome": "success"},
            {"intent_text": "计算 2+2", "actions": [{"tool": "calc", "args": {}}], "outcome": "success"},
            {"intent_text": "计算 3+3", "actions": [{"tool": "calc", "args": {}}], "outcome": "success"},
        ]

        patterns = await miner.mine(experiences, min_cluster_size=3)
        # 应该至少发现 2 个聚类（天气和计算），每个 size>=3
        assert len(patterns) >= 2
        names = [p["representative_intent"] for p in patterns]
        assert any("天气" in n for n in names)
        assert any("计算" in n for n in names)

    @pytest.mark.asyncio
    async def test_mine_returns_empty_when_too_few_experiences(self):
        miner = PatternMiner()
        await miner.initialize()
        patterns = await miner.mine([{"intent_text": "只有一个"}], min_cluster_size=3)
        assert patterns == []


class TestMemoryManagerSkillFlow:
    @pytest.mark.asyncio
    async def test_try_skill_returns_none_when_library_empty(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()
        result = await mgr.try_skill("查询北京天气")
        assert result is None

    @pytest.mark.asyncio
    async def test_try_skill_matches_after_adding_skill(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()

        skill = {
            "skill_name": "query_weather",
            "trigger_patterns": ["查询北京天气", "查询{city}天气"],
            "parameters": ["city"],
            "actions": [{"tool": "weather_query", "args": {"city": "{city}"}}],
        }
        mgr.skill_library.add_skill(skill)

        result = await mgr.try_skill("查询上海天气")
        assert result is not None
        assert result["skill_name"] == "query_weather"
        assert result["parameters"]["city"] == "上海"
        assert result["actions"][0]["args"]["city"] == "上海"

    @pytest.mark.asyncio
    async def test_try_skill_returns_none_when_params_missing(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()

        skill = {
            "skill_name": "query_weather",
            "trigger_patterns": ["查询{city}天气"],
            "parameters": ["city"],
            "actions": [{"tool": "weather_query", "args": {"city": "{city}"}}],
        }
        mgr.skill_library.add_skill(skill)

        # "随便聊聊" 无法提取 city 参数
        result = await mgr.try_skill("随便聊聊")
        assert result is None

    @pytest.mark.asyncio
    async def test_learning_cycle_distills_skills(self, temp_db_path):
        mgr = MemoryManager(base_path=temp_db_path)
        await mgr.initialize()

        # 注入足够的相似成功经验
        for city in ["北京", "上海", "广州", "深圳", "杭州"]:
            mgr.record_experience(
                intent_text=f"查询{city}天气",
                actions=[{"tool": "weather_query", "args": {"city": city}}],
                outcome="success",
                source="mcp_audit",
            )

        await mgr.run_skill_learning_cycle()

        results = await mgr.skill_library.retrieve("查询成都天气", top_k=1, threshold=0.50)
        assert len(results) >= 1
        assert results[0]["skill_name"] == "query_weather"
