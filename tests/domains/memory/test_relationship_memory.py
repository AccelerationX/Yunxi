"""Persistent relationship memory tests."""

import pytest

from domains.memory.manager import MemoryManager


def test_relationship_memory_persists_preferences_episodes_and_promises(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    memory.record_preference("远最喜欢喝冰美式，不加糖")
    memory.record_episode("上次一起看了电影《星际穿越》")
    memory.record_promise("云汐答应明天提醒远继续验收日常模式")

    reloaded = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    summary = reloaded.get_memory_summary()

    assert "冰美式" in summary
    assert "星际穿越" in summary
    assert "明天提醒" in summary


def test_capture_relationship_memory_uses_conservative_rules(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    captured = memory.capture_relationship_memory(
        "我最喜欢冰美式，不加糖；明天记得提醒我继续看部署方案。"
    )

    assert captured["preferences"]
    assert captured["promises"]
    assert "冰美式" in memory.get_memory_summary()
    assert "提醒" in memory.get_memory_summary()


@pytest.mark.asyncio
async def test_memory_manager_close_releases_subsystems(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    await memory.initialize()

    await memory.close()
